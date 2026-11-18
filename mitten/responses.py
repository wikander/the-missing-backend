"""Setting status, headers and bodies on mitmproxy requests and responses."""

import json
import logging
import random

from mitmproxy import http

from mitten.http_status import BODYLESS_STATUS_CODES, HTTP_STATUS_PHRASES
from mitten.mock_file import MockPart

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


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


def set_status(response: http.Response, code: int) -> None:
    """Set the status code and its reason phrase.

    mitmproxy doesn't update the reason when status_code changes, and its
    own table has older phrases, so the reason always comes from
    http_status. Unregistered codes get an empty reason.
    """
    response.status_code = code
    response.reason = HTTP_STATUS_PHRASES.get(code, "")


def build_response(part: MockPart, rng: random.Random) -> http.Response:
    """A short-circuit: the response a request part with a statusCode makes."""
    assert part.statusCode is not None
    response = http.Response.make()
    set_status(response, part.statusCode.pick(rng))
    apply_part(response, part)
    return response


def apply_response_part(response: http.Response, part: MockPart, rng: random.Random) -> None:
    """Override what a response part sets; leave the rest as it is."""
    if part.statusCode is not None:
        set_status(response, part.statusCode.pick(rng))
    apply_part(response, part)


def _body_length(response: http.Response) -> int:
    return len(response.raw_content or b"")


def drop_forbidden_body(response: http.Response, source: str) -> None:
    """Remove a body the status code doesn't allow (RFC 9110).

    1xx, 204, 205 and 304 responses have no content. A client doesn't read a
    body sent with them anyway, and the leftover bytes would be taken as the
    start of the next response on the same connection.
    """
    code = response.status_code
    if not (100 <= code < 200 or code in BODYLESS_STATUS_CODES):
        return
    length = _body_length(response)
    if code not in (205, 304):
        # A 1xx or 204 must not have Content-Length at all, not even the
        # "0" mitmproxy gives every response it makes.
        response.headers.pop("Content-Length", None)
    if not length:
        return
    response.content = b""
    if code == 304:
        # A 304 describes the stored response, so Content-Length and
        # Content-Type may stay, giving the length the full body would have.
        response.headers["Content-Length"] = str(length)
    else:
        response.headers.pop("Content-Type", None)
        if code == 205:
            response.headers["Content-Length"] = "0"
        else:
            response.headers.pop("Content-Length", None)
    logging.warning(f"{source}: a {code} response must not have a body; {length} bytes dropped")


def drop_head_body(response: http.Response) -> None:
    """Answer a HEAD request like the GET would be answered, minus the body.

    Content-Length keeps the length the GET body would have, as RFC 9110
    allows for HEAD; Content-Type and the other headers stay as they are.
    """
    length = _body_length(response)
    if not length:
        return
    response.content = b""
    response.headers["Content-Length"] = str(length)
