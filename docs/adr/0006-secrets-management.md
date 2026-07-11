# 0006 — Secrets management backend (OPEN)

## Context
`platform/aecp_platform/secrets.py` defines a `SecretProvider` interface
with a working `EnvSecretProvider` (dev/CI only) and a stub
`KMSSecretProvider`. Production needs a real backend before any tenant
data is at risk.

## Decision
Not yet made. This ADR exists so the decision is tracked instead of
silently defaulting to environment variables in production.

## Consequences of leaving this open
`KMSSecretProvider.get()` raises `NotImplementedError` deliberately —
this should be a loud failure, not a silent fallback to plaintext env
vars, until this ADR is resolved.

## Options under consideration
- Cloud-native (AWS Secrets Manager / GCP Secret Manager): lowest
  operational overhead if AECP commits to a single cloud.
- HashiCorp Vault: cloud-agnostic, supports dynamic short-lived
  credentials (pairs well with the mTLS/scoped-credential model in ADR
  0003), more operational surface to run.

Resolve before the first production deployment; update this ADR's
Decision section rather than opening a new one.
