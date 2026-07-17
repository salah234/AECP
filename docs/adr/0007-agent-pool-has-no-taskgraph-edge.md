# 0007 — Agent Pool has no network or client edge to TaskGraph

## Context
`deploy/k8s/networkpolicy/agents-edges.yaml` deliberately restricts Agent
Pool pods to egress only to Coordinator and State:

> agent worker pods may only reach the Coordinator (for
> scheduling/escalation) and the State Layer (for hydration). They have
> NO edge to taskgraph, integration, observability, the gateway, or —
> critically — each other.

The original `agents/app` scaffold (pre-implementation) wired a
`taskgraph_client` directly into `ContextHydrator` and `LifecycleManager`
so hydration and spawn-time risk-tier/ownership lookups could call
`TaskGraphService.GetTaskNode` directly. That contradicts the
NetworkPolicy above and `taskgraph-ingress`'s NetworkPolicy, which only
allows ingress from Coordinator, Gateway, and Integration — not Agents.
Implementing the scaffold as originally wired would have produced code
that passes unit tests but is unreachable in the deployed topology.

## Decision
Agent Pool never calls TaskGraphService, directly or otherwise. Instead:

- `SpawnSessionRequest` (proto/agents/v1/agents.proto) now carries
  `ownership: aecp.common.v1.OwnershipBoundary` and
  `task_node_snapshot: bytes` (an opaque, Coordinator-forwarded
  serialization of `taskgraph.v1.TaskNode`). The Coordinator — which
  already has a TaskGraph edge and already called `GetTaskNode`/
  `Schedule` to make the assignment decision — populates these fields
  when it calls `SpawnSession`.
- `AgentSession` carries the same two fields, captured verbatim at spawn
  time, so a handoff-spawned replacement session is rehydrated from data
  already on the session record rather than by re-querying anything.
- `ContextHydrator` and `LifecycleManager` depend only on the session
  registry (via `LifecycleManager`) and `StateClient` — never a
  TaskGraph client. `agents/app/config.py` accordingly has no
  `taskgraph_addr` setting.

This keeps CLAUDE.md's key invariant intact one level up the stack too:
just as an agent session should never need to inspect another agent's
work directly, Agent Pool should never need to ask TaskGraph "what does
this task look like?" — the Coordinator, which is "the only component
allowed to make cross-agent tradeoffs," already knows and hands it down.

## Consequences
- Agent Pool's actual dependency graph now matches its NetworkPolicy
  exactly: Coordinator (inbound), Coordinator + State (outbound).
- Coordinator (once implemented) must forward `ownership` and
  `task_node_snapshot` on every `SpawnSession` call; if it omits them,
  Agent Pool has no fallback path to fetch them itself. This is an
  explicit coupling Coordinator's own implementation must honor.
- `HydrateContextResponse.context_bundle`'s `relevant_interface_contracts`
  and `relevant_decision_log_entries` remain empty for now:
  `proto/state/v1/state.proto` has no "contracts/decisions relevant to
  task X" query RPC (only exact-id `GetInterfaceContract` and a
  write-only `RecordDecision`). This is a separate, pre-existing proto
  gap, not something this ADR resolves — `agents/app/hydration.py`
  documents it inline.

## Alternatives considered
- Add a new TaskGraph-reading RPC on CoordinatorService for Agent Pool to
  call (e.g. `GetTaskContext`) and keep the NetworkPolicy's Coordinator-only
  edge: rejected for now as unnecessary indirection — Coordinator already
  has the data in hand at the moment it decides to spawn a session, so
  forwarding it costs nothing and avoids an extra round trip.
- Loosen `agents-edges.yaml` to also allow Agent Pool → TaskGraph:
  rejected — widens the blast radius of a compromised agent-pool pod for
  no functional benefit, and contradicts the NetworkPolicy file's own
  stated intent.
