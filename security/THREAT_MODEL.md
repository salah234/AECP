# Threat Model

Living document. Update it in the same PR that changes a trust boundary
— a stale threat model is worse than none, because it creates false
confidence.

## Trust boundaries

```
Internet
   │  (TLS, OIDC authorization-code flow)
   ▼
Gateway  ── only component reachable from outside the cluster network
   │  (mTLS, SPIFFE service identity)
   ▼
Coordinator ── mediates ALL cross-service and cross-agent coordination
   │
   ├── TaskGraph ── State ── Integration ── Observability
   │
   └── Agent Pool
          │  (mTLS, per-session scoped credential, sandboxed execution)
          ▼
       Agent Session (untrusted: executes model-generated actions)
```

## Actors and what they can do

| Actor | Authenticates via | Can reach | Cannot reach |
|---|---|---|---|
| Human user (EM/reviewer) | OIDC via Gateway | Gateway REST API, scoped to their tenant | Any internal gRPC service directly |
| Agent session | Short-lived scoped credential from Agent Pool | Coordinator, State (read-scoped to its own task) | TaskGraph, Integration, Observability, Gateway, **other agent sessions** |
| Coordinator | mTLS service identity | TaskGraph, State, Agent Pool, Observability | — (it is the hub) |
| Internal service (TaskGraph/State/Integration/Observability) | mTLS service identity | Postgres (own schema only), Observability (audit writes) | Other tenants' rows (RLS), other services outside its declared callers |

## Primary threats and mitigations

1. **Cross-tenant data leak.** Mitigated by RLS on every tenant-scoped
   table (`platform/aecp_platform/dbtenant.py`) plus server-derived
   tenant context that a client can never override
   (`gateway/app/tenancy.py`).
2. **Compromised or misbehaving agent session reaching another agent's
   sandbox or task.** Mitigated at the network layer
   (`deploy/k8s/networkpolicy/agents-edges.yaml`) and at the application
   layer (`platform/aecp_platform/identity.AllowList`) — defense in
   depth, not either/or.
3. **Agent self-escalating beyond its granted risk tier.** Mitigated by
   `taskgraph/app/risk_tier.py` being the only place a grant is issued,
   and `coordinator/app/tradeoff.py` being the only place an escalation
   is approved; an agent that tries to act outside its grant should hit
   an authorization check, not a convention.
4. **Secret exposure via logs or error messages.**
   `platform/aecp_platform/secrets.SecretValue` has no unredacted
   `__repr__`/`__str__` by design.
5. **Supply-chain compromise of a dependency.** Mitigated by CI running
   `pip-audit`/`npm audit`, container image scanning (Trivy), and
   pinned, lockfile-based installs (see `.github/workflows/ci.yml`).
6. **Tampering with the audit trail after a security incident.**
   Mitigated by the audit_events table being append-only at the database
   role level (see `observability/migrations/0001_audit_trail.sql`), not
   just by application code discipline.

## Open items

- Agent sandbox concrete implementation (`agents/app/sandbox.py`) is not
  yet chosen (gVisor/Firecracker/container-only) — this is a Tier 3
  decision and needs its own ADR before implementation starts.
- Secrets backend (KMS vs Vault) is not yet chosen — see
  `docs/adr/0006-secrets-management.md`.
