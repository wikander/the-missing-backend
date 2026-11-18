"""The Missing Backend: a mitmproxy addon that mocks or alters HTTP traffic.

Mocks are read from mitten-mock*.json files. The format is described in
docs/mock-format.md, and the reasons for it in docs/adr/.
"""

import asyncio
import json
import logging
import os
import random
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from mitmproxy import command, ctx, exceptions, http
from mitmproxy.addonmanager import Loader
from mitmproxy.http import HTTPFlow
from mitmproxy.net.http import status_codes

JSON = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]

MOCK_FILE_PREFIX = "mitten-mock"
MOCK_FILE_SUFFIX = ".json"
DISABLED_PREFIX = "_x_"
METADATA_KEY = "missingbe"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"

KNOWN_MOCK_KEYS = {"path", "method", "request", "response"}
KNOWN_PART_KEYS = {"statusCode", "headers", "body"}

# Prefixed so it can't collide with a query parameter the real backend uses.
SLEEP_PARAM = "mitten-sleep"
DEFAULT_SLEEP_OPTION = "mitten_default_sleep"
DEFAULT_SLEEP = "[50,700]"


class MockFileError(ValueError):
    """A mock file that can't be loaded."""


class SleepError(ValueError):
    """A sleep value that isn't an integer or a [min, max] pair."""


@dataclass(frozen=True)
class Sleep:
    """A delay in milliseconds: fixed when min_ms == max_ms, else random."""

    min_ms: int
    max_ms: int

    def pick(self, rng: random.Random) -> int:
        return rng.randint(self.min_ms, self.max_ms)


NO_SLEEP = Sleep(0, 0)


def _is_ms(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_sleep(raw: Any) -> Sleep:
    """Parse a decoded JSON sleep value: 500 or [200, 800], in milliseconds."""
    if _is_ms(raw):
        return Sleep(raw, raw)
    if isinstance(raw, list) and len(raw) == 2 and all(_is_ms(v) for v in raw):
        if raw[0] > raw[1]:
            raise SleepError(f"{raw}: min is greater than max")
        return Sleep(raw[0], raw[1])
    raise SleepError(
        f"{json.dumps(raw)}: expected milliseconds as a non-negative integer or [min, max]"
    )


def parse_sleep_text(text: str) -> Sleep:
    """Parse a sleep value given as text, such as a query parameter or option."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raise SleepError(
            f"{text!r}: expected milliseconds as a non-negative integer or [min, max]"
        ) from None
    return parse_sleep(raw)


@dataclass
class Header:
    key: str
    values: list[str]


@dataclass
class MockPart:
    """The request or response part of a mock. Every field is optional."""

    statusCode: Optional[int] = None
    headers: list[Header] = field(default_factory=list)
    body: JSON = None  # None means "not set"

    def sets_content_type(self) -> bool:
        return any(h.key.lower() == "content-type" for h in self.headers)


@dataclass
class Mock:
    path: str
    source: str
    method: Optional[str] = None  # upper case; None matches any method
    request: Optional[MockPart] = None
    response: Optional[MockPart] = None


# ---- Parsing ---------------------------------------------------------------


def parse_headers(raw: Any, where: str) -> list[Header]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise MockFileError(f"{where}.headers must be an object")

    headers = []
    for key, values in raw.items():
        if key.startswith(DISABLED_PREFIX):
            continue
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise MockFileError(f"{where}.headers.{key} must be a list of strings")
        kept = [v for v in values if not v.startswith(DISABLED_PREFIX)]
        if kept:
            headers.append(Header(key=key, values=kept))
    return headers


def parse_part(raw: Any, where: str) -> Optional[MockPart]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise MockFileError(f"{where} must be an object")

    for key in raw.keys() - KNOWN_PART_KEYS:
        logging.warning(f"{where}: unknown field '{key}' ignored")

    status = raw.get("statusCode")
    if status is not None and (
        isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 999
    ):
        raise MockFileError(f"{where}.statusCode must be an integer between 100 and 999")

    return MockPart(
        statusCode=status,
        headers=parse_headers(raw.get("headers"), where),
        body=raw.get("body"),
    )


def parse_mock(data: Any, source: str) -> Mock:
    if not isinstance(data, dict):
        raise MockFileError("expected a JSON object")

    path = data.get("path")
    if not isinstance(path, str) or not path:
        raise MockFileError("path is required and must be a non-empty string")

    method = data.get("method")
    if method is not None and (not isinstance(method, str) or not method):
        raise MockFileError("method must be a non-empty string")

    for key in data.keys() - KNOWN_MOCK_KEYS:
        logging.warning(f"{source}: unknown field '{key}' ignored")

    return Mock(
        path=path,
        source=source,
        method=method.upper() if method else None,
        request=parse_part(data.get("request"), "request"),
        response=parse_part(data.get("response"), "response"),
    )


def load_mock_files(directory: str) -> list[Mock]:
    """Read and validate every mitten-mock*.json file in a directory.

    Raises MockFileError naming the file if any of them is invalid, so a
    caller can keep its previous mocks.
    """
    mocks = []
    for entry in sorted(os.scandir(directory), key=lambda e: e.name):
        if not (
            entry.is_file()
            and entry.name.startswith(MOCK_FILE_PREFIX)
            and entry.name.endswith(MOCK_FILE_SUFFIX)
        ):
            continue
        try:
            with open(entry.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            mocks.append(parse_mock(data, entry.name))
        except (json.JSONDecodeError, MockFileError) as e:
            raise MockFileError(f"{entry.name}: {e}") from e
        logging.info(f"Mock file loaded: {entry.name}")
    return mocks


# ---- Applying mocks ----------------------------------------------------------


def apply_part(message: http.Message, part: MockPart) -> None:
    """Set a part's headers and body on a request or response.

    Headers go first, so a Content-Type from the mock decides how the body
    text is encoded.
    """
    for header in part.headers:
        message.headers.set_all(header.key, header.values)

    if part.body is not None:
        if not part.sets_content_type():
            message.headers["Content-Type"] = JSON_CONTENT_TYPE
        message.text = json.dumps(part.body)


def build_response(part: MockPart) -> http.Response:
    assert part.statusCode is not None
    response = http.Response.make(part.statusCode)
    apply_part(response, part)
    return response


def apply_response_part(response: http.Response, part: MockPart) -> None:
    if part.statusCode is not None:
        response.status_code = part.statusCode
        response.reason = status_codes.RESPONSES.get(part.statusCode, "")
    apply_part(response, part)


# ---- Addon -------------------------------------------------------------------


class MissingBe:
    def __init__(self):
        self.mocks: list[Mock] = []
        # The mock each live flow matched, for the response hook. Kept out of
        # flow.metadata, which must stay serializable (ADR 0004).
        self.flow_mocks: weakref.WeakKeyDictionary[HTTPFlow, Mock] = (
            weakref.WeakKeyDictionary()
        )
        # No delay until configure() reads the option, so tests that build the
        # addon directly don't wait.
        self.default_sleep: Sleep = NO_SLEEP
        self.rng = random.Random()

    def comparePaths(self, abstractPath: str, path: str):
        abstractPathParts = [p for p in abstractPath.split("/") if p]
        pathParts = [p for p in path.split("/") if p]

        has_wildcard = any(p.startswith(":*") for p in abstractPathParts)

        if not has_wildcard and len(abstractPathParts) != len(pathParts):
            return None

        params = {}
        for a, b in zip(abstractPathParts, pathParts):
            if a.startswith(":*"):
                return params
            if a.startswith(":"):
                params[a[1:]] = b
            elif a != b:
                return None

        return params

    def getAbsolutePath(self, path_str: str):
        return str((Path.cwd() / Path(path_str)).resolve())

    def loadMockFiles(self, path: str) -> None:
        absolutePath = self.getAbsolutePath(path)
        logging.info(f"Loading mock files from {absolutePath}")
        # Only replaced when every file is valid.
        self.mocks = load_mock_files(absolutePath)
        logging.info(f"{len(self.mocks)} mock(s) loaded")

    def findMock(self, flow: HTTPFlow) -> Optional[Mock]:
        path = flow.request.path.split("?", 1)[0]
        method = flow.request.method.upper()
        candidates = [
            mock
            for mock in self.mocks
            if (mock.method is None or mock.method == method)
            and self.comparePaths(mock.path, path) is not None
        ]
        return random.choice(candidates) if candidates else None

    def load(self, loader: Loader):
        loader.add_option(
            name="mock_dir",
            typespec=str,
            default=".",
            help="Directory to load mitten-mock*.json files from, relative to the current directory.",
        )
        loader.add_option(
            name=DEFAULT_SLEEP_OPTION,
            typespec=str,
            default=DEFAULT_SLEEP,
            help=(
                f"Delay in ms for requests without ?{SLEEP_PARAM}=: an integer, "
                "or [min,max] for a random delay. 0 turns it off."
            ),
        )

    def configure(self, updated: set[str]):
        if DEFAULT_SLEEP_OPTION in updated:
            text = getattr(ctx.options, DEFAULT_SLEEP_OPTION)
            try:
                self.default_sleep = parse_sleep_text(text)
            except SleepError as e:
                raise exceptions.OptionsError(f"{DEFAULT_SLEEP_OPTION}: {e}") from e

        if "mock_dir" in updated:
            directory = ctx.options.mock_dir
            if not os.path.isdir(self.getAbsolutePath(directory)):
                raise exceptions.OptionsError(f"mock_dir: not a directory: {directory}")
            try:
                self.loadMockFiles(directory)
            except MockFileError as e:
                raise exceptions.OptionsError(f"mock_dir: {e}") from e

    @command.command("missingbe.reload")
    def reload(self) -> None:
        """Re-read the mock files from mock_dir."""
        try:
            self.loadMockFiles(ctx.options.mock_dir)
        except MockFileError as e:
            raise exceptions.CommandError(f"Reload failed, keeping previous mocks: {e}") from e

    def requestSleep(self, flow: HTTPFlow) -> Sleep:
        """The ?mitten-sleep= value, removed from the request, or the default."""
        # Only touch the query when the param is there: changing it re-encodes
        # the whole query string (?flag becomes ?flag=).
        if SLEEP_PARAM not in flow.request.query:
            return self.default_sleep
        # pop: the param is for the proxy only, so it must not reach the server.
        text = flow.request.query.pop(SLEEP_PARAM)
        try:
            return parse_sleep_text(text)
        except SleepError as e:
            logging.warning(f"{SLEEP_PARAM} ignored, using {DEFAULT_SLEEP_OPTION}: {e}")
            return self.default_sleep

    async def request(self, flow: HTTPFlow):
        sleep_ms = self.requestSleep(flow).pick(self.rng)
        if sleep_ms:
            flow.metadata[METADATA_KEY] = {"sleep_ms": sleep_ms}
            # asyncio.sleep only pauses this flow; time.sleep would block
            # mitmproxy's event loop and stall every other request too.
            await asyncio.sleep(sleep_ms / 1000)

        mock = self.findMock(flow)
        if mock is None:
            return

        logging.info(f"{flow.request.method} {flow.request.path} matched {mock.source}")
        self.flow_mocks[flow] = mock
        flow.metadata.setdefault(METADATA_KEY, {})["mock"] = mock.source

        part = mock.request
        if part is None:
            return
        if part.statusCode is not None:
            flow.response = build_response(part)  # short-circuit
        else:
            apply_part(flow.request, part)

    def response(self, flow: HTTPFlow):
        mock = self.flow_mocks.get(flow)
        if mock is None or mock.response is None:
            return
        assert flow.response is not None  # mitmproxy only calls this hook with a response
        apply_response_part(flow.response, mock.response)


addons = [MissingBe()]
