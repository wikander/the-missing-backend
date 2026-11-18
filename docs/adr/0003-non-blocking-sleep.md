# 3. Non-blocking `?sleep=` delay

Date: 2026-11-17

## Status

Accepted. The parameter is renamed and given a default by
[ADR 0005](0005-mitten-sleep.md).

## Context

A `?sleep=<ms>` query parameter delays a request, to simulate a slow
backend. It was implemented with `time.sleep` in the `request` hook.
mitmproxy runs all flows on one asyncio event loop, so `time.sleep` stopped
every flow, not only the delayed one: a plain request sent during a 2 s
sleep took 1.8 s.

The parameter was also forwarded to the real server on requests that were
not mocked.

## Decision

- The `request` hook is `async` and waits with `await asyncio.sleep(...)`,
  which pauses only the current flow.
- The parameter is read with `flow.request.query.pop("sleep", None)`, which
  removes it before the request can be forwarded.

Blocking work in hooks in general should either use async libraries, or be
moved off the event loop with `asyncio.to_thread`. The older
`@concurrent` decorator works too, but runs the hook in a worker thread, so
shared state would need to be thread-safe.

## Consequences

- With the fix, the plain request in the same test took 3 ms.
- The real server never sees `sleep`. A backend that itself uses a `sleep`
  query parameter cannot receive it through the proxy.
