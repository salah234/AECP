# 0005 — gRPC as the universal internal transport

## Context
CLAUDE.md requires gRPC between Coordinator and agent workers, and more
broadly prefers boring, typed, inspectable data structures over implicit
coordination via prompting or loosely-typed REST/JSON.

## Decision
Every internal service-to-service edge uses gRPC, with `.proto` files in
`/proto` as the single source of truth for request/response shapes
across all six backend services. The Gateway is the only place REST
exists (for the dashboard and any future external API), and it is a
translation layer over the same generated stubs, not a separate schema.

## Consequences
- One schema definition per concept (e.g. `TaskNode`) shared by every
  language/service that touches it — no drift between a Python
  dataclass and a hand-written REST contract.
- Requires `buf` in the toolchain (`proto/buf.yaml`, `proto/buf.gen.yaml`)
  and a `make proto-gen` step before a service's generated stubs exist;
  this is intentionally not run automatically on every build to keep
  generated code changes visible in diffs.
- Slightly more upfront ceremony than ad-hoc REST for a new internal
  endpoint — acceptable given how much of AECP's job is precisely
  making inter-agent agreement a typed, inspectable artifact rather than
  an implicit understanding.

## Alternatives considered
- REST/FastAPI internally with Pydantic schemas: rejected — would still
  need a shared-schema mechanism to avoid drift, and gRPC gets one for
  free plus streaming support the Agent Pool's session lifecycle may
  eventually need.
