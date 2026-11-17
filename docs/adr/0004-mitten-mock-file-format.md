# 4. `mitten-mock` file format with request and response parts

Date: 2026-11-17

## Status

Accepted

## Context

The original `response*.json` files described one canned response: `path`,
`statusCode`, `headers`, `body`. In practice:

- Only GET requests with a non-empty body were ever answered from a mock.
- `headers` were added to the forwarded request, not to the response, and
  their values were comma-joined.
- There was no way to match on method, to forward a request with changes, or
  to change a real server response.

## Decision

Mock files are named `mitten-mock*.json` and have this shape (full reference
in [`docs/mock-format.md`](../mock-format.md)):

```json
{
  "path": "/test",
  "method": "GET",
  "request":  { "statusCode": 200, "headers": {}, "body": {} },
  "response": { "statusCode": 200, "headers": {}, "body": {} }
}
```

- **Matching:** `path` is required. `method` is optional; when present it
  must match, case-insensitively. When several mocks match, one is picked at
  random (variants).
- **`request`, applied in the `request` hook:**
  - With `statusCode`: the request is short-circuited. A response is built
    from the object's `statusCode`, `headers` and `body`, and the server is
    not contacted.
  - Without `statusCode`: the request goes to the server, with the object's
    `headers` and `body` applied to it first.
- **`response`, applied in the `response` hook:** `statusCode`, `headers`
  and `body` override the response. This also applies to a response built
  by a short-circuit.
- **Applying parts:**
  - A header in the mock replaces all existing values of that header. Each
    value is sent as a separate header line (no comma-joining), so
    `Set-Cookie` works.
  - `body` is any JSON value and replaces the whole body, serialized as
    JSON. Unless the mock's headers set `Content-Type`,
    `application/json; charset=utf-8` is set.
- **`_x_` prefix** on a header name or value disables it, as before.
- **Validation:** a malformed file stops loading with an error naming the
  file. On reload, the previously loaded mocks stay active.
- The matched mock is remembered per flow in a weak dictionary, not in
  `flow.metadata`, because objects in `flow.metadata` make flows impossible
  to save (`mitmdump -w`). `flow.metadata["missingbe"]` holds only the mock's
  file name, for visibility in the UI.

## Consequences

- Any method and status can be mocked, including empty bodies and error
  responses.
- A request or a real response can be partially altered instead of
  replaced.
- Breaking change: `response*.json` files are no longer loaded. The example
  files have been converted.
- `utils/curl-2-mock` still generates the old format.
- Not supported yet: removing headers, merging a body into the real JSON,
  non-JSON bodies, and choosing a variant other than randomly.
