# The Missing Backend

A mitmproxy addon (`missingbe.py`) that answers or alters HTTP traffic from
`mitten-mock*.json` mock files, and passes everything else through to the
real backend.

## Layout

- `missingbe.py`: the addon. Mock parsing and the request/response hooks.
- `constants.py`: registered HTTP status codes and reason phrases.
- `test_missingbe.py`: pytest tests.
- `example-responses/`: example mock files.
- `test-server.py`: Flask echo server on port 3000 for trying it out.
- `utils/curl-2-mock/`: Rust tool that turns curl output into a mock file
  (still generates the old `response` format).
- `docs/mock-format.md`: the mock file reference. Keep it in sync with the
  code.
- `docs/adr/`: Architecture Decision Records.

## Commands

```bash
python -m pytest -q
mitmdump -s ./missingbe.py --mode reverse:http://localhost:3000 --set mock_dir=./example-responses --set connection_strategy=lazy -p 3001
```

The mitmproxy installed by Homebrew has its own Python; tests need a
virtualenv with `requirements.txt` installed.

## Conventions

- Record design decisions as a new ADR in `docs/adr/` (see ADR 0001) and add
  it to `docs/adr/README.md`.
- Add user-facing changes to `CHANGELOG.md` under `[Unreleased]`.
- Hooks must not block: use `async def` and `await`, never `time.sleep` or
  other blocking I/O in a hook (ADR 0003).
- Don't put non-JSON-serializable objects in `flow.metadata`; it breaks
  saving flows with `mitmdump -w` (ADR 0004).
- The user commits to `main` and pushes themselves.
