# CLAUDE.md

## Project

**AECP — Autonomous Engineering Coordination Platform**

An operating system that manages AI software engineers like a real engineering manager.

## The Actual Problem

Do not optimize this codebase for "AI writes better code." That problem is largely solved upstream by the model providers. Every design decision here should instead serve one goal:

> **Coordinating multiple autonomous engineers over weeks or months on a single real codebase without the system rotting.**

Concretely, that means AECP's job is to solve the things a human EM solves, not the things a senior IC solves:

- Decomposing ambiguous work into units an agent can actually own
- Deciding what can run in parallel vs. what must be serialized
- Preventing two agents from silently invalidating each other's work
- Preserving context and decisions across sessions, restarts, and agent handoffs
- Knowing when to escalate to a human vs. when to let an agent proceed
- Maintaining a single coherent architecture as dozens of agent-authored PRs land over months
- Detecting drift, regressions, and scope creep before they compound

If a proposed feature makes agents write better individual diffs but doesn't help with the above, it's out of scope for this repo.

## Non-Goals

- Not a better code-completion model or prompting framework.
- Not a CI/CD tool. AECP sits *above* CI, deciding what gets built and in what order.
- Not a single-agent coding assistant. Single-agent orchestration is a solved sub-problem AECP treats as a primitive (via Claude Code / equivalent), not something to reinvent.
- Not trying to remove humans from the loop — trying to make the human loop cheap (EM-level oversight of N agents, not IC-level review of every line).

## System Architecture

AECP is organized around five subsystems. Each has its own directory and should be understandable in isolation.

### 1. Coordinator (`/coordinator`)
The "engineering manager." Owns the task graph, assigns work to agents, decides sequencing, and is the only component allowed to make cross-agent tradeoffs. Stateless workers should never talk to each other directly — everything routes through the Coordinator so there is one place that understands the whole picture.

### 2. Task Graph (`/taskgraph`)
Work is never a flat queue. Every unit of work is a node with explicit:
- **Dependencies** (blocks / blocked-by)
- **Ownership boundary** (which files/modules/interfaces it may touch)
- **Definition of done** (tests, acceptance criteria, review gate)
- **Risk tier** (see Escalation Policy below)

Decomposition quality is the single highest-leverage part of this system. A vague task handed to an agent produces convincing-looking, wrong work. Prefer many small, sharply-bounded nodes over few large ones.

### 3. Agent Pool (`/agents`)
Manages agent lifecycle: spin-up, context hydration, handoff, and teardown. Each agent session is treated as disposable and stateless — all durable knowledge lives in the State & Memory Layer, never in an agent's own scratch context. An agent that dies or times out mid-task must be resumable by a *different* agent instance with no loss of continuity.

### 4. State & Memory Layer (`/state`)
The institutional memory a human team gets for free through Slack threads, standups, and tribal knowledge. AECP has to build this explicitly:
- **Decision log** — why something was built a certain way, not just what
- **Ownership map** — which agent/task last touched which module and why
- **Interface contracts** — the boundaries agents must not silently change
- **Drift detector** — flags when live code diverges from the decision log's assumptions

Treat this layer as the source of truth. Task graph and agent context are derived views over it, not the other way around.

### 5. Conflict & Integration Layer (`/integration`)
Handles what happens when parallel agents produce overlapping or contradictory changes:
- Static ownership boundaries prevent most conflicts before they happen (see Task Graph)
- Semantic conflict detection catches cases where two changes are individually valid but jointly incoherent (e.g., two agents both "fix" the same invariant in incompatible ways)
- Merge policy is explicit per risk tier — some conflicts auto-resolve, some block on a human

## Escalation Policy (Risk Tiers)

Every task node gets a risk tier at creation time. This is the primary lever for human-in-the-loop cost control.

| Tier | Example | Human involvement |
|------|---------|-------------------|
| 0 — Mechanical | Rename, formatting, test scaffolding | None; auto-merge on green CI |
| 1 — Local | Bug fix within one owned module | Async review, no blocking |
| 2 — Structural | New interface, cross-module change | Human approval required before merge |
| 3 — Architectural | Anything touching the State & Memory Layer's own contracts, security boundaries, or public API | Human-authored task only; agents may propose, never merge |

An agent must never self-assign a higher tier than the task graph gave it. If a task turns out to be bigger than its tier suggests, the correct behavior is to halt and re-escalate to the Coordinator, not to proceed.

## Repository Structure

```
/coordinator     # scheduling, assignment, cross-agent tradeoffs
/taskgraph       # task decomposition, dependency + ownership model
/agents          # agent lifecycle, context hydration, handoff protocol
/state           # decision log, ownership map, interface contracts, drift detection
/integration     # conflict detection, merge policy, semantic diff review
/observability   # dashboards, agent activity logs, escalation audit trail
/gateway         # human-facing API/BFF: OIDC session termination, tenant resolution, REST→gRPC proxy — the ONLY component reachable from outside the private network
/dashboard       # Next.js/TypeScript EM-facing UI, talks only to /gateway
/platform        # shared Python library: config, secrets, service identity (mTLS), tenant isolation (Postgres RLS), telemetry, error taxonomy — every backend service depends on this instead of reimplementing cross-cutting concerns
/proto           # source-of-truth gRPC contracts for every internal service edge (see Tech Stack)
/deploy          # docker-compose (local dev), Kubernetes manifests + NetworkPolicies, Terraform (cloud infra)
/security        # SECURITY.md (reporting policy), THREAT_MODEL.md (trust boundaries — keep in sync with any boundary change)
/docs            # architecture decision records (ADRs) — see below
```

## Architecture Decision Records

Any change to how coordination itself works (not the target codebase AECP manages, but AECP's own internals) requires an ADR in `/docs/adr/`. Format: context, decision, consequences, alternatives considered. This repo eats its own dog food — AECP's own history should be as legible as the histories it enforces on the systems it manages.

## Tech Stack & Conventions

- All backend subsystems (`/coordinator`, `/taskgraph`, `/agents`, `/state`, `/integration`, `/observability`, `/gateway`) are Python (FastAPI for HTTP health/admin surfaces, grpcio for internal RPC). See `docs/adr/0002-all-python-backend.md`. Favor explicit state machines over implicit control flow for coordination logic (e.g. `coordinator/app/statemachine.py`) — this is a coordination system, correctness of sequencing matters more than throughput.
- Dashboard: Next.js + TypeScript (`/dashboard`), talks only to `/gateway` over REST — never directly to an internal service.
- Internal transport: gRPC for every service-to-service edge, not just Coordinator↔agent workers. `/proto` is the single source of truth for request/response shapes; see `docs/adr/0005-grpc-as-internal-transport.md`.
- `/platform` (`aecp_platform` Python package): shared config loading, secrets access, service identity, tenant isolation, telemetry, and error taxonomy. Every backend service depends on it instead of reimplementing these.
- State layer: Postgres for structured state (task graph, ownership map, decision log), object storage for large context artifacts.
- No agent-to-agent direct communication paths, ever, even for "efficiency." All coordination is mediated. This is enforced at two layers, not one: `deploy/k8s/networkpolicy` denies the network path outright, and `platform/aecp_platform/identity.AllowList` denies it at the application layer even if the network path somehow existed.
- Prefer boring, inspectable data structures (explicit DAGs, typed schemas) over emergent/implicit coordination via prompting. If two agents need to agree on something, that agreement should be a row in a table, not a shared understanding inferred from context.

## Security & Multi-Tenancy

AECP is a multi-tenant, production-grade SaaS handling agents with write access to real customer codebases — security is not an add-on layer, it is load-bearing for the product to be trustworthy at all. See `/security/THREAT_MODEL.md` for the full breakdown; the binding conventions:

- **Human auth**: OIDC via a pluggable external provider at the Gateway only (`gateway/app/auth.py`). AECP never stores a password. See `docs/adr/0003-oidc-human-auth-mtls-service-identity.md`.
- **Service auth**: mutual TLS with SPIFFE-style workload identities between every internal service (`platform/aecp_platform/identity.py`). No static shared secret or long-lived API key for internal calls, ever.
- **Agent credentials**: each agent session gets a short-lived, narrowly-scoped credential issued per-session by the Agent Pool (`agents/app/identity.py`), revoked on termination/handoff — never a long-lived key.
- **Multi-tenancy**: every tenant-scoped Postgres table has `tenant_id` + a `FORCE ROW LEVEL SECURITY` policy. Application code only ever touches the database through `platform/aecp_platform/dbtenant.TenantScopedPool`, which derives tenant context server-side (from a verified session or service identity) and refuses to run unscoped. See `docs/adr/0004-postgres-rls-multitenancy.md`. A migration that adds a tenant-scoped table without an RLS policy is a bug, not a follow-up.
- **Secrets**: accessed only via `platform/aecp_platform/secrets.SecretProvider`. `EnvSecretProvider` is dev/CI only; production secrets backend is still an open decision — see `docs/adr/0006-secrets-management.md`. No secret is ever logged (`SecretValue` has no unredacted `repr`/`str`).
- **Audit**: every security-relevant event (auth/authz failure, risk-tier escalation, ownership violation) and every Tier 2+ state change is written to the append-only audit trail (`observability/app/audit.py`), which is append-only at the database role level, not merely by application convention.
- **Sandboxing**: agent sessions execute untrusted, model-generated actions and are isolated per-session (no shared filesystem or network namespace, egress restricted to declared dependencies) — see `agents/app/sandbox.py`. The concrete sandbox technology is an open Tier 3 decision, not yet an ADR.

## Development Workflow

1. Changes to `/coordinator`, `/taskgraph`, `/state`, or `/integration` are themselves Tier 2+ by default — they change how *all* other work gets coordinated. Changes to `/platform` (identity, tenancy, secrets) or the mTLS/RLS/NetworkPolicy configuration in `/deploy` are Tier 3 — they are security boundaries per the Escalation Policy table above.
2. Every PR touching scheduling or conflict logic needs a test that simulates at least two concurrent agents (see `coordinator/tests/test_concurrent_agents.py`, `integration/tests/test_concurrent_agents.py` — CI's `concurrency-test-guard` job checks these files exist, but does not substitute for reviewing what they assert).
3. Never let the task graph and the state layer diverge silently — any schema change to one requires an explicit migration note for the other.
4. Any change to a trust boundary (auth, tenancy, sandboxing, network policy) must update `/security/THREAT_MODEL.md` in the same PR.

## Key Invariant

**No agent should ever need to ask "did someone else already do this, or contradict this?" by inspecting other agents' work directly.** If that question is even possible to ask, the Coordinator and State Layer have failed at their job. Design toward agents that only ever need to look at: their task node, their ownership boundary, and the state layer's contracts.