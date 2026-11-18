"""The Missing Backend: a mitmproxy addon that mocks or alters HTTP traffic.

Mocks are read from mitten-mock*.json files. The format is described in
docs/mock-format.md, and the reasons for it in docs/adr/.

This file is the addon: its options, its state and the hooks. The building
blocks are in the mitten package. mitmproxy reloads this file when it
changes, but not the mitten modules: restart mitmproxy after editing those
(ADR 0010).
"""

import asyncio
import logging
import os
import random
import weakref
from pathlib import Path
from typing import Any, Optional

from mitmproxy import command, ctx, exceptions, http
from mitmproxy.addonmanager import Loader
from mitmproxy.http import HTTPFlow

from mitten.cors import CorsMode, add_cors_headers, build_preflight_response, is_preflight
from mitten.mock_file import Mock, MockFileError, load_mock_files
from mitten.responses import (
    apply_part,
    apply_response_part,
    build_response,
    drop_forbidden_body,
    drop_head_body,
)
from mitten.sleep import NO_SLEEP, Sleep, SleepError, parse_sleep_text

METADATA_KEY = "missingbe"

MOCK_DIR_OPTION = "mock_dir"

# Prefixed so it can't collide with a query parameter the real backend uses.
SLEEP_PARAM = "mitten-sleep"
DEFAULT_SLEEP_OPTION = "mitten_default_sleep"
DEFAULT_SLEEP = "[50,700]"

CORS_OPTION = "mitten_cors"
DEFAULT_CORS = CorsMode.MOCKS


def absolute_path(path: str) -> str:
    """A path relative to the current directory, made absolute."""
    return str((Path.cwd() / Path(path)).resolve())


def flow_metadata(flow: HTTPFlow) -> dict[str, Any]:
    """This addon's entry in flow.metadata, created if missing.

    Only JSON values go in it, or saving flows with mitmdump -w breaks
    (ADR 0004).
    """
    return flow.metadata.setdefault(METADATA_KEY, {})


class MissingBe:
    def __init__(self):
        self.mocks: list[Mock] = []
        # The mock each live flow matched, for the response hook. Kept out of
        # flow.metadata, which must stay serializable (ADR 0004).
        self.flow_mocks: weakref.WeakKeyDictionary[HTTPFlow, Mock] = weakref.WeakKeyDictionary()
        # No delay until configure() reads the option, so tests that build the
        # addon directly don't wait.
        self.default_sleep: Sleep = NO_SLEEP
        self.cors: CorsMode = DEFAULT_CORS
        self.rng = random.Random()

    # ---- Options and commands -------------------------------------------------

    def load(self, loader: Loader):
        loader.add_option(
            name=MOCK_DIR_OPTION,
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
        loader.add_option(
            name=CORS_OPTION,
            typespec=str,
            default=DEFAULT_CORS.value,
            choices=[mode.value for mode in CorsMode],
            help=(
                "CORS for browser frontends on another origin. mocks: answer preflights "
                "and add CORS headers for short-circuited requests. all: for every "
                "request, overriding the server's CORS (only for local use). off: never."
            ),
        )

    def configure(self, updated: set[str]):
        if CORS_OPTION in updated:
            self.configure_cors(getattr(ctx.options, CORS_OPTION))
        if DEFAULT_SLEEP_OPTION in updated:
            self.configure_default_sleep(getattr(ctx.options, DEFAULT_SLEEP_OPTION))
        if MOCK_DIR_OPTION in updated:
            self.configure_mock_dir(getattr(ctx.options, MOCK_DIR_OPTION))

    def configure_cors(self, value: str) -> None:
        # mitmproxy only uses choices for help text; --set accepts anything.
        try:
            self.cors = CorsMode(value)
        except ValueError:
            choices = ", ".join(mode.value for mode in CorsMode)
            raise exceptions.OptionsError(f"{CORS_OPTION}: {value!r} is not one of {choices}") from None
        if self.cors == CorsMode.ALL:
            logging.warning(
                f"{CORS_OPTION}=all: every response can be read by any website, "
                "with cookies. Only use it with a proxy nothing else browses through."
            )

    def configure_default_sleep(self, text: str) -> None:
        try:
            self.default_sleep = parse_sleep_text(text)
        except SleepError as e:
            raise exceptions.OptionsError(f"{DEFAULT_SLEEP_OPTION}: {e}") from e

    def configure_mock_dir(self, directory: str) -> None:
        if not os.path.isdir(absolute_path(directory)):
            raise exceptions.OptionsError(f"{MOCK_DIR_OPTION}: not a directory: {directory}")
        try:
            self.load_mock_files(directory)
        except MockFileError as e:
            raise exceptions.OptionsError(f"{MOCK_DIR_OPTION}: {e}") from e

    @command.command("missingbe.reload")
    def reload(self) -> None:
        """Re-read the mock files from mock_dir."""
        try:
            self.load_mock_files(getattr(ctx.options, MOCK_DIR_OPTION))
        except MockFileError as e:
            raise exceptions.CommandError(f"Reload failed, keeping previous mocks: {e}") from e

    def load_mock_files(self, directory: str) -> None:
        path = absolute_path(directory)
        logging.info(f"Loading mock files from {path}")
        # Only replaced when every file is valid.
        self.mocks = load_mock_files(path)
        logging.info(f"{len(self.mocks)} mock(s) loaded")

    # ---- Matching --------------------------------------------------------------

    def matching_mocks(self, path: str, method: str) -> list[Mock]:
        path = path.split("?", 1)[0]
        method = method.upper()
        if method == "HEAD":
            method = "GET"  # HEAD is a GET without the body (RFC 9110)
        return [mock for mock in self.mocks if method in mock.methods and mock.path.matches(path)]

    def find_mock(self, flow: HTTPFlow) -> Optional[Mock]:
        """The mock with the most specific path (ADR 0009). Mocks with equally
        specific paths are variants, picked at random."""
        candidates = self.matching_mocks(flow.request.path, flow.request.method)
        if not candidates:
            return None
        best = max(mock.path.specificity for mock in candidates)
        return random.choice([m for m in candidates if m.path.specificity == best])

    def answers_preflight(self, request: http.Request) -> bool:
        """Whether mitten_cors has the addon answer this preflight itself.

        With "mocks", only when the real request may be short-circuited: then
        no server will answer it, so the server can't answer the preflight
        either. Requests a mock forwards keep the server's own CORS.
        """
        if self.cors == CorsMode.ALL:
            return True
        if self.cors == CorsMode.MOCKS:
            method = request.headers["Access-Control-Request-Method"]
            return any(mock.short_circuits for mock in self.matching_mocks(request.path, method))
        return False

    def request_sleep(self, flow: HTTPFlow) -> Sleep:
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

    # ---- Hooks -----------------------------------------------------------------

    async def request(self, flow: HTTPFlow):
        sleep_ms = self.request_sleep(flow).pick(self.rng)
        if sleep_ms:
            flow_metadata(flow)["sleep_ms"] = sleep_ms
            # asyncio.sleep only pauses this flow; time.sleep would block
            # mitmproxy's event loop and stall every other request too.
            await asyncio.sleep(sleep_ms / 1000)

        if is_preflight(flow.request) and self.answers_preflight(flow.request):
            logging.info(f"CORS preflight for {flow.request.path} answered ({CORS_OPTION}={self.cors})")
            flow.response = build_preflight_response(flow.request)
            flow_metadata(flow)["cors_preflight"] = True
            return

        mock = self.find_mock(flow)
        if mock is None:
            return

        logging.info(f"{flow.request.method} {flow.request.path} matched {mock.source}")
        self.flow_mocks[flow] = mock
        flow_metadata(flow)["mock"] = mock.source

        if mock.request is None:
            return
        if mock.short_circuits:
            flow.response = build_response(mock.request, self.rng)
            flow_metadata(flow)["short_circuit"] = True
        else:
            apply_part(flow.request, mock.request)

    def response(self, flow: HTTPFlow):
        assert flow.response is not None  # mitmproxy only calls this hook with a response
        mock = self.flow_mocks.get(flow)
        if mock is not None:
            if mock.response is not None:
                apply_response_part(flow.response, mock.response, self.rng)
            # Also for a server's own 304 that a response part gave a body.
            drop_forbidden_body(flow.response, mock.source)
            if flow.request.method.upper() == "HEAD":
                drop_head_body(flow.response)
        self.apply_cors(flow)

    def apply_cors(self, flow: HTTPFlow) -> None:
        assert flow.response is not None
        origin = flow.request.headers.get("Origin")
        metadata = flow.metadata.get(METADATA_KEY, {})
        if not origin or metadata.get("cors_preflight"):
            return
        if self.cors == CorsMode.ALL or (self.cors == CorsMode.MOCKS and metadata.get("short_circuit")):
            add_cors_headers(flow.response, origin)


addons = [MissingBe()]
