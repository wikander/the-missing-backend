"""The mitten-mock*.json format: data classes, parsing and loading.

Files are validated when they load, so the hooks only see well-formed mocks.
The format is described in docs/mock-format.md.
"""

import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from mitten.http_status import RANDOM_STATUS_CODES
from mitten.paths import PathPattern

JSON = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]

MOCK_FILE_PREFIX = "mitten-mock"
MOCK_FILE_SUFFIX = ".json"
DISABLED_PREFIX = "_x_"

KNOWN_MOCK_KEYS = {"path", "method", "request", "response"}
KNOWN_PART_KEYS = {"statusCode", "headers", "body"}

STATUS_FORMAT = "an integer 100-999, a 1-2 digit prefix such as 4 or 40, or an array of those"
METHOD_FORMAT = 'method is required: a method such as "GET", or an array such as ["GET", "POST"]'


class MockFileError(ValueError):
    """A mock file that can't be loaded."""


# ---- Data classes --------------------------------------------------------------


@dataclass
class Header:
    key: str
    values: list[str]


@dataclass(frozen=True)
class StatusSpec:
    """A statusCode: one or more choices, each a single code or a prefix's codes.

    A choice is picked first and then a code within it, so in [2, 404] the
    404 comes up half the time.
    """

    choices: tuple[tuple[int, ...], ...]

    def pick(self, rng: random.Random) -> int:
        return rng.choice(rng.choice(self.choices))


@dataclass
class MockPart:
    """The request or response part of a mock. Every field is optional."""

    statusCode: Optional[StatusSpec] = None  # named as in the JSON
    headers: list[Header] = field(default_factory=list)
    body: JSON = None  # None means "not set"

    def sets_content_type(self) -> bool:
        return any(h.key.lower() == "content-type" for h in self.headers)


@dataclass
class Mock:
    path: PathPattern
    source: str  # the file name, for log messages
    methods: tuple[str, ...]  # upper case, never HEAD
    request: Optional[MockPart] = None
    response: Optional[MockPart] = None

    @property
    def short_circuits(self) -> bool:
        """Whether the request part answers the request itself."""
        return self.request is not None and self.request.statusCode is not None


# ---- Parsing -------------------------------------------------------------------


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


def parse_status_choice(raw: Any, where: str) -> tuple[int, ...]:
    """One code (404), or every registered code starting with a prefix (4, 40)."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise MockFileError(f"{where}.statusCode: {json.dumps(raw)} is not {STATUS_FORMAT}")
    if 100 <= raw <= 999:
        return (raw,)
    if 1 <= raw <= 99:
        prefix = str(raw)
        codes = tuple(c for c in RANDOM_STATUS_CODES if str(c).startswith(prefix))
        if not codes:
            raise MockFileError(
                f"{where}.statusCode: no status code to pick starts with {raw} "
                "(1xx codes are never picked at random)"
            )
        return codes
    raise MockFileError(f"{where}.statusCode: {raw} is not {STATUS_FORMAT}")


def parse_status(raw: Any, where: str) -> Optional[StatusSpec]:
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            raise MockFileError(f"{where}.statusCode: an array needs at least one code")
        return StatusSpec(tuple(parse_status_choice(r, where) for r in raw))
    return StatusSpec((parse_status_choice(raw, where),))


def parse_part(raw: Any, where: str) -> Optional[MockPart]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise MockFileError(f"{where} must be an object")

    for key in raw.keys() - KNOWN_PART_KEYS:
        logging.warning(f"{where}: unknown field '{key}' ignored")

    return MockPart(
        statusCode=parse_status(raw.get("statusCode"), where),
        headers=parse_headers(raw.get("headers"), where),
        body=raw.get("body"),
    )


def parse_methods(raw: Any) -> tuple[str, ...]:
    """The required method field: one method or an array of them, upper-cased.

    HEAD is rejected: HEAD requests use the GET mocks, so a mock can't answer
    HEAD differently from GET.
    """
    if raw is None:
        raise MockFileError(METHOD_FORMAT)
    items = raw if isinstance(raw, list) else [raw]
    if not items or not all(isinstance(m, str) and m.strip() for m in items):
        raise MockFileError(METHOD_FORMAT)
    methods = tuple(m.strip().upper() for m in items)
    if "HEAD" in methods:
        raise MockFileError(
            "method HEAD isn't allowed: HEAD requests use the GET mocks, answered without the body"
        )
    return methods


def parse_mock(data: Any, source: str) -> Mock:
    if not isinstance(data, dict):
        raise MockFileError("expected a JSON object")

    path = data.get("path")
    if not isinstance(path, str) or not path:
        raise MockFileError("path is required and must be a non-empty string")

    methods = parse_methods(data.get("method"))

    for key in data.keys() - KNOWN_MOCK_KEYS:
        logging.warning(f"{source}: unknown field '{key}' ignored")

    return Mock(
        path=PathPattern.parse(path),
        source=source,
        methods=methods,
        request=parse_part(data.get("request"), "request"),
        response=parse_part(data.get("response"), "response"),
    )


# ---- Loading -------------------------------------------------------------------


def is_mock_file(name: str) -> bool:
    return name.startswith(MOCK_FILE_PREFIX) and name.endswith(MOCK_FILE_SUFFIX)


def load_mock_files(directory: str) -> list[Mock]:
    """Read and validate every mitten-mock*.json file in a directory.

    Raises MockFileError naming the file if any of them is invalid, so a
    caller can keep its previous mocks.
    """
    mocks = []
    for entry in sorted(os.scandir(directory), key=lambda e: e.name):
        if not (entry.is_file() and is_mock_file(entry.name)):
            continue
        try:
            with open(entry.path, "r", encoding="utf-8") as file:
                data = json.load(file)
            mocks.append(parse_mock(data, entry.name))
        except (json.JSONDecodeError, MockFileError) as e:
            raise MockFileError(f"{entry.name}: {e}") from e
        logging.info(f"Mock file loaded: {entry.name}")
    return mocks
