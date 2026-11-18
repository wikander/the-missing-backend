# 9. The most specific path wins

Date: 2026-11-18

## Status

Accepted

## Context

When several mocks matched a request, one was picked at random. That is
what makes several files with the same `path` work as variants, but it also
applied between different patterns: with `/users/me` and `/users/:id`, a
request for `/users/me` got either mock. A mock for a special case could not
be relied on, and the only way around it was to avoid overlapping patterns.

The matching itself had a bug: a pattern with `:*` skipped the length check,
and only the segments the path had were compared, so `/a/b/:*` matched `/a`.
Ranking matches would let such a false match compete with real ones, and
even win.

## Decision

- A `:*` pattern requires every segment before the `:*`, and matches zero or
  more segments after it, so `/a/:*` matches `/a`.
- When several mocks match, only those with the most specific `path` are
  kept, and one of them is picked at random. Patterns are compared segment
  by segment from the left. At the first segment where they differ, a
  literal beats a `:param`, which beats `:*`, and a pattern that ends there
  beats one with `:*` (`/a` beats `/a/:*` for `/a`).
- Only the kind of each segment counts. `/users/:id` and `/users/:name` are
  equally specific and stay variants of each other.
- Only mocks whose `method` matches are ranked.

Left-to-right comparison was chosen over counting literal segments, which
ties `/a/:x/c` and `/:y/b/c`, and because it is the rule most HTTP routers
use, so mock files behave the way the routes they stand in for do.

## Consequences

- A mock for a special case, such as `/users/me` next to `/users/:id`,
  always wins, without changes to the general mock.
- Variants still need the same pattern. Making a specific path random again
  takes variants of that specific path.
- A file set that relied on overlapping patterns being mixed at random
  behaves differently: the less specific mocks are no longer used for those
  paths.
