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

### Changed

- **Breaking:** mock files are named `mitten-mock*.json` and use the new
  format. `response*.json` files are no longer loaded.
- **Breaking:** the `missingbe.load <path>` command is replaced by the
  `mock_dir` option and `missingbe.reload`.
- Mock headers are set on the response (or on the forwarded request when
  they are in a `request` part), with each value as its own header line
  instead of comma-joined.

### Fixed

- `?sleep=` no longer blocks every other request while one is delayed
  ([ADR 0003](docs/adr/0003-non-blocking-sleep.md)).
- The `sleep` query parameter is no longer forwarded to the server.
- The README referred to `missing_be.py` instead of `missingbe.py`.
