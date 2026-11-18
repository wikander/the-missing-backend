"""CORS: answering preflights and letting a cross-origin page read responses.

Which requests get this is the addon's decision (the mitten_cors option,
ADR 0008); this module only knows what the headers look like.
"""

from enum import StrEnum

from mitmproxy import http

from mitten.responses import set_status


class CorsMode(StrEnum):
    OFF = "off"  # no CORS handling
    MOCKS = "mocks"  # for requests a mock short-circuits
    ALL = "all"  # for every request, replacing the server's CORS


def is_preflight(request: http.Request) -> bool:
    """A CORS preflight: an OPTIONS request a browser sends before the real one."""
    return (
        request.method.upper() == "OPTIONS"
        and "Origin" in request.headers
        and "Access-Control-Request-Method" in request.headers
    )


def merge_vary(response: http.Response, *names: str) -> None:
    """Add names to the Vary header, keeping the ones already there."""
    existing = [v.strip() for v in response.headers.get("Vary", "").split(",") if v.strip()]
    lower = {v.lower() for v in existing}
    response.headers["Vary"] = ", ".join(existing + [n for n in names if n.lower() not in lower])


def build_preflight_response(request: http.Request) -> http.Response:
    """Allow whatever the preflight asks for, for the origin that asks."""
    response = http.Response.make()
    set_status(response, 204)
    response.headers.pop("Content-Length", None)  # a 204 has no content
    response.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
    response.headers["Access-Control-Allow-Methods"] = request.headers["Access-Control-Request-Method"]
    if "Access-Control-Request-Headers" in request.headers:
        response.headers["Access-Control-Allow-Headers"] = request.headers[
            "Access-Control-Request-Headers"
        ]
    response.headers["Access-Control-Allow-Credentials"] = "true"
    # No Access-Control-Max-Age: browsers then cache the answer for 5 s only,
    # so changing mitten_cors takes effect right away.
    merge_vary(response, "Origin", "Access-Control-Request-Method", "Access-Control-Request-Headers")
    return response


def add_cors_headers(response: http.Response, origin: str) -> None:
    """Let the page from origin read this response, cookies and headers included.

    Echoing the origin, not "*", is what allows credentials.
    """
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    exposed = sorted(
        {name for name in response.headers.keys() if not name.lower().startswith("access-control-")}
    )
    if exposed:
        response.headers["Access-Control-Expose-Headers"] = ", ".join(exposed)
    merge_vary(response, "Origin")
