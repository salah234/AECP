# 0002 — All-Python backend, Next.js dashboard

## Context
AECP's backend spans six services with different concerns (scheduling,
graph validation, sandboxed execution, persistence, conflict detection,
audit). A prior draft of this repo mandated Go for the Coordinator and
Integration layers specifically. That mandate has been superseded.

## Decision
Every backend subsystem (`coordinator`, `taskgraph`, `agents`, `state`,
`integration`, `observability`, `gateway`) is implemented in Python
(FastAPI for HTTP health/admin surfaces, grpcio for internal RPC).
Postgres remains the structured-state store. The dashboard is Next.js/
TypeScript. `platform/` is a shared Python library every service depends
on for config, secrets, identity, tenancy, telemetry, and error handling.

## Consequences
- One language across the backend simplifies review, tooling, and
  dependency/vulnerability scanning (single ecosystem in CI).
- Python's weaker static-typing guarantees relative to Go are mitigated
  by: mandatory type hints, mypy/pyright in CI, and pydantic models at
  every service boundary (see each service's `schema.py`).
- Explicit state machines (see `coordinator/app/statemachine.py`) are
  still required for scheduling logic — the language change does not
  relax CLAUDE.md's preference for explicit control flow over implicit
  coordination via prompting.

## Alternatives considered
- Go for Coordinator/Integration only, Python elsewhere: rejected to
  avoid a language boundary exactly at the highest-traffic internal gRPC
  edge, and to keep one CI/dependency-scanning pipeline.
- REST instead of gRPC internally: rejected — see ADR 0005.
