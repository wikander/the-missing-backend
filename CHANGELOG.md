# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `mitten-mock*.json` mock files with optional `method` matching and
  separate `request` and `response` parts. See
  [docs/mock-format.md](docs/mock-format.md) and
  [ADR 0004](docs/adr/0004-mitten-mock-file-format.md).
- A `request` part with `statusCode` short-circuits the request; without
  `statusCode` it alters the request before forwarding.
- A `response` part overrides status, headers and body of the response, also
  on real server responses.
- Mocks for any HTTP method, with empty bodies and any status code.
- Mock files are validated on load, with errors naming the file. A failed
  reload keeps the previous mocks.
- `mock_dir` option for the mock directory, and the `missingbe.reload`
  command ([ADR 0002](docs/adr/0002-mock-directory-as-mitmproxy-option.md)).
- Architecture Decision Records in `docs/adr/`.
- Bruno collection in `bruno/` for the test server, with environments for
  calling it directly and through mitmproxy.
- `mitten_default_sleep` option: every request without its own delay waits
  a random 50–700 ms by default; `0` turns it off
  ([ADR 0005](docs/adr/0005-mitten-sleep.md)).
- Delays can be a random range, `[min,max]` in ms, as well as a fixed
  number.
- `statusCode` can be a 1–2 digit prefix (`4`, `40`) for a random registered
  code, or an array of codes and prefixes to pick from, picked again for
  every request ([ADR 0006](docs/adr/0006-random-status-codes.md)).
- `constants.py` with the registered HTTP status codes and their reason
  phrases.
- `mitten_cors` option, `mocks` by default: CORS preflights for requests a
  mock short-circuits are answered by the addon, and short-circuited
  responses get CORS headers, so mocked endpoints work from a frontend on
  another origin. `all` does it for every request; `off` never
  ([ADR 0008](docs/adr/0008-cors-for-mocks.md)).

### Changed

- **Breaking:** `method` is required in mock files, as a string or an array
  of strings. `HEAD` is not allowed in it: HEAD requests use the `GET` mocks
  and get the GET response without the body
  ([ADR 0007](docs/adr/0007-required-method-and-no-forbidden-bodies.md)).
- **Breaking:** the `sleep` query parameter is renamed `mitten-sleep`, so it
  can't collide with a backend's own `sleep` parameter. `sleep` is now
  forwarded to the server like any other parameter.
- **Breaking:** requests through the proxy are delayed 50–700 ms by default.
  Use `--set mitten_default_sleep=0` for the old behaviour.
- **Breaking:** mock files are named `mitten-mock*.json` and use the new
  format. `response*.json` files are no longer loaded.
- **Breaking:** the `missingbe.load <path>` command is replaced by the
  `mock_dir` option and `missingbe.reload`.
- Reason phrases come from `constants.py` with the RFC 9110 wording (for
  example `Request Timeout`, not `Request Time-out`). 444 and 499, which
  aren't registered, now get an empty reason.
- Mock headers are set on the response (or on the forwarded request when
  they are in a `request` part), with each value as its own header line
  instead of comma-joined.
- The test server's `/test` endpoints are replaced by `/short-circuit` and
  `/fall-through`, each with its own example mocks, and it logs every
  request with its path, headers and body.

### Fixed

- Mocked 1xx, 204, 205 and 304 responses, and HEAD responses, were sent with
  a body, which corrupted the next response on the connection. Bodies are now
  dropped for those statuses, and HEAD requests get the GET response without
  the body.
- The README's commands use `--set connection_strategy=lazy`, without which
  mitmproxy fails every request, mocked or not, when the backend is down.
- `?sleep=` no longer blocks every other request while one is delayed
  ([ADR 0003](docs/adr/0003-non-blocking-sleep.md)).
- The `sleep` query parameter is no longer forwarded to the server.
- The README referred to `missing_be.py` instead of `missingbe.py`.
