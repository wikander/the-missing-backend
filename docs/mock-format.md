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
| `method` | no | string | HTTP method to match, case-insensitive. Missing: any method. |
| `request` | no | [part](#parts) | Applied in the `request` hook. |
| `response` | no | [part](#parts) | Applied in the `response` hook. |

Unknown top-level fields are ignored with a warning in the log.

### Parts

`request` and `response` have the same fields, all optional:

| Field | Type | Meaning |
|---|---|---|
| `statusCode` | integer, 100–999 | See below. |
| `headers` | object: name → list of strings | Headers to set. See [Headers](#headers). |
| `body` | any JSON value | Replaces the whole body. `null` counts as not set. |

## What happens to a request

1. **Match.** The query string is ignored. A mock matches when its `path`
   pattern matches and, if it has a `method`, the method matches. If several
   mocks match, one is picked at random, so several files with the same
   `path` work as variants.
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

## Path patterns

| Pattern | Matches | Doesn't match |
|---|---|---|
| `/api/people` | `/api/people` | `/api/people/1` |
| `/api/people/:id` | `/api/people/1` | `/api/people/1/films` |
| `/api/:*` | `/api/people`, `/api/people/1/films` | `/other` |

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
