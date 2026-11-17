# 1. Record architecture decisions

Date: 2026-11-17

## Status

Accepted

## Context

Design decisions in this project have so far been made in conversations and
only survived as code. The reasons behind them (why an option instead of a
command, why `async`, why a certain file format) are easy to lose, and
without them it is hard to know what can safely be changed.

## Decision

We record architecture decisions as Architecture Decision Records (ADRs), as
described by Michael Nygard:
<https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions>.

- One Markdown file per decision in `docs/adr/`, named
  `NNNN-short-title.md` with a running four-digit number.
- Sections: Status, Context, Decision, Consequences.
- An ADR is not edited once accepted, apart from its status. A changed
  decision gets a new ADR that supersedes the old one, and the old one's
  status becomes "Superseded by NNNN".

User-facing changes are listed in `CHANGELOG.md`.

## Consequences

The reasons for a design stay next to the code. Each new decision costs a
short document. Decisions made before this ADR are recorded after the fact
in ADRs 0002 and 0003.
