# 2. Mock directory as a mitmproxy option

Date: 2026-11-12

## Status

Accepted

## Context

Mock files were loaded from the current working directory when the script
was imported, before mitmproxy had applied any options. A
`missingbe.load <path>` command could load another directory, but it can only
be run from the mitmproxy or mitmweb prompt, not from mitmdump, and nothing
showed which directory was loaded.

## Decision

- The addon registers a `mock_dir` option (default `.`) in the `load` hook.
- Mocks are loaded in the `configure` hook, at startup and whenever
  `mock_dir` changes. A path that is not a directory is rejected with an
  `OptionsError`.
- The `missingbe.load <path>` command is replaced by `missingbe.reload`,
  which takes no arguments and re-reads `mock_dir`.

## Consequences

- The mock directory can be set with `--set mock_dir=...`, in
  `~/.mitmproxy/config.yaml`, or in the options editor, and is visible with
  the other options.
- There is a single source of truth for which directory is loaded.
- Edited mock files are not picked up automatically; run `missingbe.reload`.
