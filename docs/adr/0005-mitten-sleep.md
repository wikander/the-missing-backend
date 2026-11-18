# 5. `mitten-sleep` delays with a random default

Date: 2026-11-18

## Status

Accepted

## Context

The `?sleep=<ms>` query parameter (ADR 0003) delayed a request by a fixed
number of milliseconds. Three things were missing:

- Behind the proxy a local server, or a short-circuited mock, answers in
  under 20 ms. That is much faster than a real remote backend, so clients
  are never tested against realistic latency unless every request sets a
  delay.
- A fixed delay doesn't vary like real latency does.
- `sleep` is a plausible name for a real backend's own query parameter, and
  the proxy removed it, so such a backend could not receive it.

Mock files are also going to get a `sleep` field in their `request` and
`response` parts, which should use the same format.

## Decision

- The query parameter is named `mitten-sleep`. The prefix keeps it apart
  from backend parameters. `sleep` is no longer touched.
- A delay is a JSON value in milliseconds: a non-negative integer, or
  `[min, max]` for a random whole number in that range, both ends included.
  The query parameter is parsed with `json.loads`, so the same parser will
  serve the mock files' `sleep` fields. Brackets were chosen over a `200-800`
  string so that JSON and the query parameter have a single shared format.
- The option `mitten_default_sleep`, `[50,700]` unless set, is used for every
  request without a `mitten-sleep` parameter, whether a mock matches or not.
  `0` turns it off. The option name is prefixed because mitmproxy options
  are shared by all loaded addons.
- The default only replaces the request-side delay. The planned
  `response.sleep` field will have no default.
- The delay is taken in the `request` hook, before matching, with
  `asyncio.sleep` as in ADR 0003. The chosen delay is stored as
  `flow.metadata["missingbe"]["sleep_ms"]`, an `int`, so flows can still be
  saved (ADR 0004).
- An invalid `mitten-sleep` value logs a warning and falls back to the
  default. An invalid option value is an option error, which stops
  mitmproxy at startup or rejects the change at runtime.
- The query string is only modified when `mitten-sleep` is present, because
  changing it makes mitmproxy re-encode the whole string (`?flag` becomes
  `?flag=`).

## Consequences

- Every request through the proxy is 50–700 ms slower by default, including
  requests that pass through to a remote backend with latency of its own.
  `--set mitten_default_sleep=0` gives the old behaviour.
- Clients that sent `?sleep=` to the proxy must switch to `?mitten-sleep=`;
  `sleep` is now forwarded to the server.
- Decimal values are rejected rather than rounded.
- Unit tests that build the addon without mitmproxy get no default delay,
  because the addon starts with none until `configure` reads the option.
