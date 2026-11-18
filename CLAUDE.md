# The Missing Backend

A mitmproxy addon (`missingbe.py`) that answers or alters HTTP traffic from
`mitten-mock*.json` mock files, and passes everything else through to the
real backend.

## Layout

- `missingbe.py`: the addon only: options, state and the request/response
  hooks.
- `mitten/`: the building blocks, one module per topic, without state or
  mitmproxy options (ADR 0010):
  - `mock_file.py`: mock data classes, parsing and loading.
  - `paths.py`: `PathPattern`, matching and specificity.
  - `sleep.py`: delay values.
  - `responses.py`: status, headers and bodies on mitmproxy messages.
  - `cors.py`: `CorsMode`, preflights and CORS headers.
  - `http_status.py`: registered HTTP status codes and reason phrases.
- `tests/`: pytest tests, one file per topic, with shared helpers in
  `tests/helpers.py` and fixtures in `tests/conftest.py`.
- `example-responses/`: example mock files.
- `test-server.py`: Flask echo server on port 3000 for trying it out.
- `utils/curl-2-mock/`: Rust tool that turns curl output into a mock file
  (still generates the old `response` format).
- `docs/mock-format.md`: the mock file reference. Keep it in sync with the
  code.
- `docs/adr/`: Architecture Decision Records.

## Commands

```bash
uv run pytest -q
mitmdump -s ./missingbe.py --mode reverse:http://localhost:3000 --set mock_dir=./example-responses --set connection_strategy=lazy -p 3001
```

Dependencies are managed with uv: `pyproject.toml` (runtime: mitmproxy;
`dev` group: pytest, Flask) and `uv.lock`. Add them with `uv add` or
`uv add --dev`, never by editing `uv.lock`. The mitmproxy installed by
Homebrew has its own Python; `uv run mitmdump ...` uses the locked version.

## Conventions

- New helpers go in the `mitten` module for their topic, or a new topic
  module; not in a generic utils file. `missingbe.py` keeps only what needs
  the addon's state or options.
- Import `mitten` modules at the top of a file, never inside a function:
  mitmproxy only has the script's folder on `sys.path` while it loads the
  script.
- Use snake_case, except data class fields named after a JSON field
  (`MockPart.statusCode`).

- Record design decisions as a new ADR in `docs/adr/` (see ADR 0001) and add
  it to `docs/adr/README.md`.
- Add user-facing changes to `CHANGELOG.md` under `[Unreleased]`.
- Hooks must not block: use `async def` and `await`, never `time.sleep` or
  other blocking I/O in a hook (ADR 0003).
- Don't put non-JSON-serializable objects in `flow.metadata`; it breaks
  saving flows with `mitmdump -w` (ADR 0004).
- The user commits to `main` and pushes themselves.
