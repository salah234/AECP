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
   │        (Coordinator also has a direct edge to Integration —
   │         deploy/k8s/networkpolicy/coordinator-edges.yaml — to call
   │         DetectConflicts before finalizing a schedule tick)
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
| Coordinator | mTLS service identity | TaskGraph, State, Agent Pool, Observability, Integration | — (it is the hub) |
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
  decision; see `docs/adr/0009-agent-sandbox-isolation-technology.md`
  (proposal, decision not yet made). `agents/app/sandbox.py`'s current
  `Sandbox` class is explicitly a non-isolating dev/test placeholder
  (scratch directory only, no process/filesystem/network isolation) so
  the rest of Agent Pool (spawn, handoff, teardown, capacity accounting)
  could be implemented and tested end-to-end without blocking on this
  decision. Do not treat it as a security boundary; it is load-bearing
  for nothing in this table.
- Agent session credentials (`agents/app/identity.py`) are HMAC-signed
  opaque tokens, not real mTLS client certificates — an interim scheme
  pending real certificate issuance; see
  `docs/adr/0008-mtls-cert-issuance-and-allowlist-rollout.md`. Same
  caveat as `AllowListInterceptor` below: acceptable for now, not the
  final mechanism.
- `platform/aecp_platform/identity.AllowList` (the application-layer
  mitigation for threat #2) **is implemented and working** — Coordinator
  is already built against it directly
  (`coordinator/app/grpc_server.py`). What's still open is the rollout:
  no environment this repo ships (`.env`, either docker-compose
  topology) sets real `MTLS_CERT_FILE`/`MTLS_KEY_FILE`/`MTLS_CA_FILE`
  values yet, so even Coordinator's real `AllowList` only ever exercises
  its documented metadata-based fallback (a caller-supplied `caller-id`,
  not a verified mTLS peer identity) in practice today — and
  taskgraph/state/agents/integration/observability each still use their
  own local, hand-rolled `AllowListInterceptor` copy (see
  `taskgraph/app/interceptors.py` and its near-identical siblings)
  rather than the shared `aecp_platform.identity.AllowList`. See
  `docs/adr/0008-mtls-cert-issuance-and-allowlist-rollout.md` for the
  full breakdown and the actual blocking decision (how certs get
  issued). The network-layer mitigation (`deploy/k8s/networkpolicy/`) is
  real and enforced independently, so defense in depth is partial, not
  absent, until this lands.
- Secrets backend (KMS vs Vault) is not yet chosen — see
  `docs/adr/0006-secrets-management.md`.
- `/integration` and `/observability` are now fully implemented (both
  were previously unimplemented stubs at the time this document's threat
  table was written) and covered by a real Docker-based system test
  exercising Coordinator↔Integration↔TaskGraph↔State↔Observability
  together (`coordinator/tests/integration/test_full_system_e2e.py`).
  Coordinator's `IntegrationClient`/`AuditClient` graceful-degradation
  paths (transport failure → logged warning, not a crash) remain in
  place and are still real, correct behavior for a genuinely unreachable
  peer — they're simply no longer the *only* path exercised, now that
  both services actually run.
- `gateway/app/main.py`'s `GET /auth/dev-login` mints a signed session
  cookie without any OIDC round-trip, bypassing the "Human user
  authenticates via OIDC" row in the actors table above. It exists only
  to unblock local dashboard testing before a real IdP is configured
  (`docs/adr/0006-secrets-management.md`/OIDC client registration are
  both still open). Gated on `OIDC_CLIENT_SECRET` being exactly the
  literal placeholder `changeme` shipped in `.env.example` — the route
  returns 404 the moment a real secret is configured, so it cannot
  activate in any environment that has actually set up OIDC. Every use
  is logged at `WARNING`. This is still a real widening of the human
  auth trust boundary while it exists (anyone who can reach gateway's
  HTTP port in a misconfigured dev/staging environment could mint a
  session for any subject/tenant/role), so it must be deleted — not just
  left dormant — once `docs/adr/0006-secrets-management.md` lands and
  real OIDC credentials are wired into every environment gateway ships
  to. Do not copy this pattern into a shipped Helm chart or K8s manifest
  default.
