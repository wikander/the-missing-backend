# 7. Required `method`, HEAD as GET, no forbidden bodies

Date: 2026-11-18

## Status

Accepted

## Context

HTTP forbids content in 1xx, 204, 205 and 304 responses, and in any response
to HEAD (RFC 9110). The addon sent a mock's `body` in all of these: a
mocked 204, 205 or 304 went out with `Content-Length: 18` and the body, and
so did a HEAD request matched by a mock without `method`. A client reads no
body in these cases, so the leftover bytes are taken as the start of the
next response on the same connection and corrupt it.

There were three ways in:

- A mock without `method` matched HEAD requests.
- A `statusCode` prefix or set (ADR 0006) could pick 204, 205 or 304 for a
  mock with a `body`.
- A fall-through mock's `response.body` was added to whatever the server
  returned, including the 304 a server sends for a conditional GET, which
  browsers make all the time.

Two ways to handle HEAD were considered:

- Never mock HEAD and always forward it. Simple, but HEAD then fails without
  a backend, and describes a different response than the mocked GET.
- Answer HEAD with the GET mocks, minus the body. This is what HTTP defines
  HEAD to be, and what server frameworks such as Flask do.

## Decision

- `method` is required: a method or an array of methods, case-insensitive.
  A file without it fails to load.
- A HEAD request matches the mocks whose `method` includes `GET`. A
  short-circuit builds the GET response; a fall-through is forwarded as
  HEAD. Before the response is sent, its body is removed and
  `Content-Length` is set to the length it had, so the headers match what a
  GET would return. This isn't logged, since it is the normal case.
- `HEAD` isn't allowed in `method`, so HEAD can never be answered
  differently from GET. A file with it fails to load.
- Before a matched flow's response is sent, a body is dropped if the status
  is 1xx, 204, 205 or 304, with a warning naming the mock file. This runs in
  the `response` hook, so it covers short-circuits and the server's own
  responses alike, and it runs before the HEAD handling. `Content-Type` and
  `Content-Length` are removed, except that 205 gets `Content-Length: 0`,
  and 304 keeps both with the length of the dropped body, which RFC 9110
  allows for a 304.
- Responses of flows no mock matched are not touched.

## Consequences

- One mock can no longer cover every method by leaving `method` out. An
  array covers the common case: `["GET", "POST", "PUT", "PATCH", "DELETE"]`.
- Existing method-less mock files stop loading, with an error naming the
  file.
- `curl -I` and other HEAD clients see what a GET returns, also without a
  backend.
- A GET mock's `request` part is applied to a forwarded HEAD as well,
  including a `body`, which a server may reject. Mock authors are expected
  to keep request bodies off GET mocks.
- OPTIONS (CORS preflight) requests are still only mocked by mocks listing
  `OPTIONS`. Cross-origin frontends without a backend will need that
  handled separately.
- A mock author who sets a body on a 204 gets a warning, not an error,
  because a prefix or set may only sometimes pick such a code.
