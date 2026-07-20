# 0008 — mTLS certificate issuance and AllowList rollout (OPEN — PROPOSAL, human decision required)

## Context
ADR 0003 already decided *that* every internal edge is mutually
authenticated via mTLS with SPIFFE-style workload identities, and
`platform/aecp_platform/identity.py` already implements the primitives
that decision needs: `MTLSConfig` (cert-backed SSL contexts),
`peer_identity()` (extracts the verified SPIFFE URI from a peer's
certificate), and `AllowList`/`_AllowListInterceptor` (per-server caller
allow-listing, with a documented metadata-based fallback for when no
verified mTLS peer identity is present).

What ADR 0003 did not decide, and what remains genuinely open, is *how
certificates actually get issued, distributed, rotated, and revoked* —
and as a direct consequence, which services run with real mTLS enforced
versus the interim fallback today:

- **Coordinator** is the only service built against the real
  `aecp_platform.identity.MTLSConfig`/`AllowList` primitives
  (`coordinator/app/grpc_server.py`'s own docstring says as much) — but
  even it falls back to an insecure channel/port whenever
  `MTLS_CERT_FILE`/`MTLS_KEY_FILE`/`MTLS_CA_FILE` are unset, which they
  are in every environment this repo ships today (`.env`,
  `deploy/docker/docker-compose.yml`, and both
  `coordinator/tests/integration/docker-compose.test.yml` compose
  topologies all leave them `""`).
- **taskgraph, state, agents, integration, observability** each have
  their own local, hand-rolled `AllowListInterceptor` (see
  `taskgraph/app/interceptors.py` and its near-identical siblings) that
  checks a plaintext, caller-supplied `caller-id` gRPC metadata value
  against an allow-list — not a cryptographically verified identity. Any
  process that can reach a service's port and set that one metadata
  field can claim to be any allowed caller.
- **gateway** has no inbound gRPC server (HTTP only) and so has no
  `AllowList` of its own, but every outbound call it makes to an internal
  service carries the same kind of self-asserted `caller-id` metadata.
- The network-layer mitigation (`deploy/k8s/networkpolicy/`) is real,
  enforced independently of any of the above, and already limits which
  pods can even attempt to reach which other pods — so this gap is
  defense-in-depth being partial, not the only layer being absent.

This is `security/THREAT_MODEL.md`'s "Open items" entry on the
`AllowList` application-layer mitigation, given its own ADR rather than
being resolved inline, because — like ADR 0006's secrets backend choice —
it requires operating real PKI infrastructure (a CA, a distribution
mechanism, a rotation policy) that this repo should not silently start
provisioning without an explicit decision.

## Decision
Not yet made. This ADR exists so the decision is tracked and the
consequence of leaving it open (every service-to-service call today is
authorized by a self-asserted string, not a cryptographic proof) stays
visible rather than fading into "that's just how it's always worked."

## Options under consideration

- **cert-manager + a self-hosted private CA (e.g. `step-ca`), on
  Kubernetes.** Lowest new-infrastructure cost if AECP is already
  committed to running on Kubernetes (`deploy/k8s` assumes this):
  `cert-manager` issues and auto-rotates short-lived certs as native K8s
  `Secret`s, mounted into each pod, no new distributed system to run
  beyond the CA itself. Weaker workload-identity semantics than SPIFFE
  proper (identity is whatever `cert-manager`'s issuer configuration
  encodes, typically namespace/service-account-derived, which needs to be
  deliberately mapped onto the `spiffe://aecp/<env>/<service>` URI shape
  `platform/aecp_platform/identity.ServiceID` already expects).
- **SPIRE (the SPIFFE reference implementation).** Directly matches the
  URI shape `identity.py` already assumes and was evidently designed
  against — `peer_identity()`'s SPIFFE URI SAN parsing needs no rework.
  Gives real workload attestation (a pod proves its identity by what it
  *is* — its K8s service account, its node — not just a bootstrapped
  secret it holds), which is the stronger security property. More
  operational surface: SPIRE Server + a SPIRE Agent per node, plus
  picking and configuring a node/workload attestor.
- **HashiCorp Vault's PKI secrets engine.** Reasonable if ADR 0006
  resolves toward Vault for secrets anyway — one system issuing both
  short-lived credentials and short-lived certs, consistent operational
  model. Redundant infrastructure to run Vault *only* for this if ADR
  0006 resolves toward a cloud-native secrets manager instead.

## Consequences of leaving this open
Every `AllowListInterceptor` across every service keeps accepting the
metadata-based `caller-id` fallback as its *only* mode, not a fallback
from a working mTLS path — because there is no working mTLS path in any
shipped environment yet. `identity.AllowList`'s own fallback logic
(`_AllowListInterceptor.intercept_service`) is written to prefer a
verified `peer_identity()` and only fall back to metadata when the
transport isn't authenticated mTLS, so *no application code needs to
change* once this ADR resolves and certs are actually issued — every
service already calls through the same `AllowList` primitive (or, for
the five services still on their own local interceptor copy, a follow-up
migration to `aecp_platform.identity.AllowList` directly, tracked
separately from this ADR's own scope: choosing *how certs get issued* is
the blocking decision, migrating each service's interceptor is
mechanical work that can start once that's chosen).

## Explicitly out of scope for this ADR (and for whoever implements it)
Per `CLAUDE.md`'s Escalation Policy, this is a Tier 3 change (security
boundary) — agents may propose (this document) but never merge a
production rollout of real mTLS unilaterally. Provisioning a real CA,
generating and distributing the first round of certs, and flipping any
environment's `MTLS_CERT_FILE`/`MTLS_KEY_FILE`/`MTLS_CA_FILE` from empty
to real values requires human sign-off on this ADR's Decision section
first.
