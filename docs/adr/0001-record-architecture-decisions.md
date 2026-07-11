# 0001 — Record architecture decisions

## Context
AECP's own coordination logic will evolve over many agent- and
human-authored PRs. Without a durable record, the reasoning behind past
decisions gets lost exactly the way CLAUDE.md says AECP exists to prevent
for the codebases it manages — we'd be failing to eat our own dog food.

## Decision
Any change to how coordination itself works requires an ADR in
`/docs/adr/`, using this format: Context, Decision, Consequences,
Alternatives considered.

## Consequences
Slightly more overhead per structural change. In exchange, a future
agent or human can answer "why is it built this way" without archaeology.

## Alternatives considered
- Rely on commit messages / PR descriptions only — rejected, they are
  not indexed or discoverable the way a fixed-location ADR directory is.
