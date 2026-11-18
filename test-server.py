"""Echo server for trying out the missing backend.

The same endpoints exist under two prefixes, matched by different mocks in
example-responses/:

- /short-circuit: the mocks answer these themselves, so through the proxy
  they never reach this server.
- /fall-through: the mocks alter the request and the response, but the
  request is still forwarded here.

Every request that reaches the server is logged, so the log shows which
requests got through the proxy and what they looked like.
"""

import logging

from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(message)s")

app = Flask(__name__)

PREFIXES = ["/short-circuit", "/fall-through"]

# Status and message per method, as a typical REST API would answer.
REPLIES = {
    "GET": (200, "hello"),
    "POST": (201, "created"),
    "PUT": (200, "replaced"),
    "PATCH": (200, "patched"),
    "DELETE": (204, None),
}

# Returned by GET, and the starting point for PATCH. Not stored: every
# request starts from this again.
DUMMY = {
    "id": 1,
    "name": "Testa Testsson",
    "email": "testa@example.com",
    "active": True,
    "score": 42.5,
    "tags": ["mock", "test"],
    "address": {"street": "Testgatan 1", "city": "Stockholm"},
    "orders": [
        {"id": 101, "total": 199.0},
        {"id": 102, "total": 49.5},
    ],
}


def response_data():
    """GET returns the dummy, PATCH merges the body into it, POST and PUT
    echo the body (or the dummy, when there is no JSON body)."""
    body = request.get_json(silent=True)
    if request.method == "PATCH" and isinstance(body, dict):
        return {**DUMMY, **body}
    if request.method in ("POST", "PUT") and body is not None:
        return body
    return DUMMY


@app.before_request
def log_request():
    lines = [f"{request.method} {request.full_path.rstrip('?')}"]
    lines += [f"  {name}: {value}" for name, value in request.headers.items()]
    body = request.get_data(as_text=True)
    if body:
        lines.append(f"  body: {body}")
    logging.info("\n".join(lines))


def echo():
    status, message = REPLIES[request.method]
    if status == 204:
        return "", 204
    return jsonify(
        {
            "message": message,
            "method": request.method,
            "path": request.path,
            "data": response_data(),
        }
    ), status


for prefix in PREFIXES:
    app.add_url_rule(
        prefix,
        endpoint=prefix,
        view_func=echo,
        methods=list(REPLIES),
    )


if __name__ == "__main__":
    app.run(port=3000, debug=True)
