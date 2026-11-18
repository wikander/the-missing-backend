# 10. Topic modules in a `mitten` package

Date: 2026-11-18

## Status

Accepted

## Context

`missingbe.py` had grown to 650 lines holding six topics: mock file parsing,
path matching, delays, response handling, CORS and the addon itself. Reading
the hooks meant scrolling past all the rest. Path patterns were parsed in
two places, the matcher and the specificity ranking, which could drift
apart. The class mixed camelCase methods with snake_case functions, and the
tests were one 800-line file.

A generic `utils.py` was considered and rejected: a file named after no
topic attracts everything, and becomes the next large file.

## Decision

- `missingbe.py` holds only the addon: options, state, the command and the
  hooks, and the helpers that need the addon's state.
- Everything else lives in a `mitten/` package, one module per topic:
  `mock_file`, `paths`, `sleep`, `responses`, `cors` and `http_status`
  (formerly `constants.py`). These modules hold no state and don't read
  mitmproxy options.
- The package isn't named `missingbe`, which would clash with the
  `missingbe.py` script.
- A path pattern is parsed once, when its file loads, into a `PathPattern`
  that both matches paths and gives its specificity.
- The CORS mode is a `StrEnum`, `CorsMode`.
- Names are snake_case, except data class fields named after JSON fields.
- Tests are in `tests/`, one file per topic, with shared helpers in
  `tests/helpers.py` and fixtures in `tests/conftest.py`.

Behaviour doesn't change.

## Consequences

- mitmproxy reloads `missingbe.py` when it is saved, but Python caches the
  imported `mitten` modules, so edits there need a restart of mitmproxy.
  ADR 0006 already accepted this for `constants.py`.
- mitmproxy puts the script's folder on `sys.path` only while loading the
  script, so `mitten` modules must be imported at the top of a file, not
  inside functions.
- A new helper has an obvious home, or a new topic module.
