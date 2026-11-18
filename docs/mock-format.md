# Mock file format

Mocks are JSON files named `mitten-mock*.json` in the directory set by the
`mock_dir` option. Each file describes one mock. Why it looks like this:
[ADR 0004](adr/0004-mitten-mock-file-format.md).

```json
{
  "path": "/api/people/:id",
  "method": "GET",
  "request": {
    "statusCode": 200,
    "headers": { "Cache-Control": ["no-cache"] },
    "body": { "name": "Luke" }
  },
  "response": {
    "headers": { "X-Mocked": ["true"] }
  }
}
```

## Fields

| Field | Required | Type | Meaning |
|---|---|---|---|
| `path` | **yes** | string | Path pattern to match. See [Path patterns](#path-patterns). |
| `method` | **yes** | string or array of strings | HTTP method(s) to match, case-insensitive: `"GET"` or `["GET", "POST"]`. `HEAD` is not allowed; see [HEAD requests](#head-requests). |
| `request` | no | [part](#parts) | Applied in the `request` hook. |
| `response` | no | [part](#parts) | Applied in the `response` hook. |

Unknown top-level fields are ignored with a warning in the log.

### Parts

`request` and `response` have the same fields, all optional:

| Field | Type | Meaning |
|---|---|---|
| `statusCode` | integer or array | See [Status codes](#status-codes). |
| `headers` | object: name → list of strings | Headers to set. See [Headers](#headers). |
| `body` | any JSON value | Replaces the whole body. `null` counts as not set. |

## What happens to a request

1. **Match.** The query string is ignored. A mock matches when its `path`
   pattern matches and the request's method is one of its `method`s. If several
   mocks match, the one with the most specific `path` wins (see
   [Path patterns](#path-patterns)). Mocks with equally specific paths are
   variants: one is picked at random for every request.
2. **`request` part.**
   - **With `statusCode`: short-circuit.** A response is built from this
     part's `statusCode`, `headers` and `body`. The server is not contacted.
   - **Without `statusCode`: alter and forward.** This part's `headers` and
     `body` are applied to the request, which then goes to the server.
   - No `request` part: the request is forwarded unchanged.
3. **`response` part.** When the response arrives, from the server or from a
   short-circuit, this part's `statusCode`, `headers` and `body` override
   it. Fields that are not set keep their value.

Requests that match no mock pass through untouched.

| `request.statusCode` | `response` part | Result |
|---|---|---|
| set | – | Fully mocked response, server not contacted |
| set | set | Mocked response, then adjusted by `response` |
| not set | – | Request altered, real response |
| not set | set | Request altered, real response adjusted |

## Status codes

| Value | Status |
|---|---|
| `404` | exactly 404. Any 100–999 is allowed, registered or not. |
| `4` | a random registered 4xx code |
| `50` | a random registered code from 500 to 509 |
| `[200, 201, 204]` | one of these at random |
| `[2, 404]` | 2xx or 404, half the time each, then a random code within the 2xx |

- **Prefixes.** An integer with one or two digits is a prefix. It picks among
  the registered codes in `mitten/http_status.py` that start with it. 1xx codes are
  never picked at random, so `1` and `10` are rejected, as is a prefix no
  code starts with (`6`, `48`).
- **Arrays** are sets of codes and prefixes, never ranges. An element is
  picked first, and then a code within it, so `[200, 200, 500]` gives 200
  two times in three. An empty array is rejected.
- **A new pick for every request.**
- **Reason phrase.** The reason (`Not Found`) is taken from `mitten/http_status.py`,
  with the RFC 9110 wording. Unregistered codes get an empty reason. HTTP/2
  and HTTP/3 have no reason phrase.
- **Bodies.** The `body` is sent whatever code is picked, including codes
  that shouldn't have one, such as 204 and 304. Use a set without them if
  that matters.

## Headers

```json
"headers": {
  "Accept": ["application/json", "text/plain"],
  "Set-Cookie": ["a=1; Path=/", "b=2; Path=/"],
  "_x_Authorization": ["Bearer xyz"],
  "X-Feature": ["on", "_x_off"]
}
```

- Each value is sent as a separate header line.
- A header in the mock replaces all existing values of that header in the
  request or response. Other headers are left as they are.
- A single string is accepted as a one-value list: `"Accept": "text/plain"`.
- **`_x_` prefix disables.** A name starting with `_x_` skips the whole
  header; a value starting with `_x_` skips that value. A header with no
  values left is skipped. JSON has no comments; this is the replacement.
- Header names are case-insensitive.

## Body

- `body` is serialized as JSON and replaces the whole body.
- If the part's headers don't set `Content-Type`, it is set to
  `application/json; charset=utf-8`.
- A short-circuit without `body` sends an empty body and no `Content-Type`.
- **No body where HTTP forbids one.** A 1xx, 204, 205 or 304 response is
  sent without a body, even if the mock sets one or a `response` part adds
  one to the server's own 304. A warning in the log names the mock file.
  `Content-Type` and `Content-Length` are removed, except that 205 gets
  `Content-Length: 0`, and 304 keeps both, with the length of the dropped
  body, since a 304 describes the full response.

## HEAD requests

A HEAD request is a GET without the body (RFC 9110), so it is handled with
the `GET` mocks:

- It matches mocks whose `method` includes `GET`.
- A short-circuit builds the same response as for GET, then removes the
  body. `Content-Length` keeps the length the body would have had, and
  `Content-Type` and the other headers stay.
- A fall-through is forwarded to the server as HEAD. A `response.body` isn't
  sent, but `Content-Length` is set to its length.
- The rules for 1xx, 204, 205 and 304 apply first, as for GET.
- Dropping the body isn't logged; for HEAD it's normal.

`HEAD` itself isn't allowed in `method`, and a file that has it fails to
load, so a HEAD request can never be answered differently from the GET.

## Path patterns

| Pattern | Matches | Doesn't match |
|---|---|---|
| `/api/people` | `/api/people` | `/api/people/1` |
| `/api/people/:id` | `/api/people/1` | `/api/people/1/films` |
| `/api/:*` | `/api`, `/api/people`, `/api/people/1/films` | `/other` |
| `/api/people/:*` | `/api/people`, `/api/people/1` | `/api` |

`:name` matches exactly one segment. `:*` matches the rest of the path, from
zero segments up, and anything after it in the pattern is ignored. Trailing
slashes and the query string don't matter.

When several patterns match, they are compared segment by segment from the
left. At the first segment where they differ, a literal beats a `:param`,
which beats `:*`, and a pattern that ends there beats one with `:*`:

| Request | Patterns | Winner |
|---|---|---|
| `/users/me` | `/users/me`, `/users/:id` | `/users/me` |
| `/users/1/orders` | `/users/:id/orders`, `/users/:*` | `/users/:id/orders` |
| `/a/b/c` | `/a/:x/c`, `/:y/b/c` | `/a/:x/c` |
| `/api` | `/api`, `/api/:*` | `/api` |

Only the kind of each segment counts, so `/users/:id` and `/users/:name` are
equally specific, and are variants of each other. Mocks for other methods
don't take part: a `POST /users/me` mock doesn't stop `GET /users/me` from
using a `GET /users/:id` mock.

## Delays: `?mitten-sleep=` and `mitten_default_sleep`

Every request through the proxy is delayed before it is matched, without
holding up other requests. The delay is in milliseconds and written as JSON:

| Value | Delay |
|---|---|
| `500` | exactly 500 ms |
| `[200,800]` | a random whole number from 200 to 800 ms, both included |
| `0` | none |

- **`?mitten-sleep=<value>`** on a request sets its delay. The parameter is
  removed before the request is forwarded, so the server never sees it. In a
  URL the brackets may be percent-encoded (`%5B200,800%5D`); with curl, use
  `-g` or encode them.
- **`mitten_default_sleep`** is the mitmproxy option used for requests
  without the parameter. It is `[50,700]` unless set:
  `--set mitten_default_sleep=0` turns it off,
  `--set mitten_default_sleep=[100,300]` changes it. An invalid value is an
  option error.
- An invalid `mitten-sleep` value is ignored with a warning in the log, and
  the default is used.
- The delay applies to every request, matched by a mock or not. The chosen
  delay is stored in the flow's metadata as `missingbe.sleep_ms`.

## Validation

Files are validated when loaded. A malformed file (invalid JSON, missing
`path`, wrong types) stops loading with an error naming the file. At startup
mitmproxy exits; on `missingbe.reload` or an option change, the previously
loaded mocks stay active.
