# 8. CORS for mocked responses

Date: 2026-11-18

## Status

Accepted

## Context

A frontend on another origin than the API, for example `localhost:5173`
calling the proxy on `localhost:3001`, is subject to CORS. The browser
sends an `OPTIONS` preflight before most API calls, and only lets the page
read a response that has `Access-Control-Allow-Origin`.

A short-circuited mock has no server behind it, so it has no CORS headers,
and its preflight either goes to a backend that may not exist (and gets
mitmproxy's 502) or matches an `OPTIONS` mock without the right headers.
Mocked endpoints then fail in the browser with CORS errors, while
fall-through endpoints work because the server's headers pass through. This
is the case in reverse mode and in regular proxy mode alike: CORS depends on
the origins in the URLs, not on whether a proxy is in between.

Making every response permissive would fix it, but would hide CORS mistakes
in the real backend, and through a regular proxy would let any website read
any other site's responses with the user's cookies.

## Decision

An option `mitten_cors` with three values, `mocks` by default:

- `off`: no CORS handling.
- `mocks`: a preflight is answered by the addon when a mock that
  short-circuits would match the real request (path and the requested
  method). Short-circuited responses get CORS headers. Everything that
  reaches the server keeps the server's own CORS.
- `all`: every preflight is answered and every response gets CORS headers,
  replacing the server's. mitmproxy logs a warning when it is set.

A preflight is an `OPTIONS` request with `Origin` and
`Access-Control-Request-Method`. It is answered with `204`, allowing the
requesting origin, the requested method and headers, and credentials, with
no `Access-Control-Max-Age`, so browsers only cache it for 5 seconds and a
change of the option takes effect at once. Other `OPTIONS` requests are
matched against mocks as before.

Responses get `Access-Control-Allow-Origin` with the request's `Origin`
echoed (not `*`, which doesn't allow credentials),
`Access-Control-Allow-Credentials: true`, `Access-Control-Expose-Headers`
listing the response's headers, and `Vary: Origin`. Requests without
`Origin` get nothing.

One option with three values was chosen over separate switches for
preflights and headers, because only these three combinations work in a
browser. mitmproxy only uses an option's `choices` for its help text, so
the addon rejects other values itself.

## Consequences

- Mocked endpoints work from a cross-origin frontend without any CORS setup
  in the mocks.
- The real backend's CORS is still tested on everything that reaches it,
  unless `all` is set.
- With `mocks` and a path whose mocks only sometimes short-circuit, the
  preflight is answered, and a request that is then forwarded depends on
  the server's CORS.
- A preflight the addon answers never reaches the server, so the server's
  own preflight handling isn't exercised for those requests.
