# 0003 — OIDC for humans, mTLS service identity for everything internal

## Context
AECP is a multi-tenant SaaS handling security-sensitive work (agents with
write access to real codebases). It needs two distinct authentication
models: human users logging into the dashboard, and services/agent
sessions calling each other internally.

## Decision
- Human users authenticate via a pluggable external OIDC provider
  (Auth0/WorkOS/Okta/generic OIDC) at the Gateway only
  (`gateway/app/auth.py`). AECP never stores a password.
- Every internal edge (Gateway→Coordinator, Coordinator→TaskGraph, etc.)
  is mutually authenticated via mTLS with SPIFFE-style workload
  identities (`platform/aecp_platform/identity.py`). No static shared
  secret or API key is used for internal calls.
- Agent sessions receive short-lived, narrowly-scoped credentials issued
  per-session by the Agent Pool (`agents/app/identity.py`), never a
  long-lived key.

## Consequences
- Smaller attack surface: AECP owns no credential store for humans.
- Requires operating (or renting) a CA for internal mTLS — see
  `deploy/terraform/modules/kms`.
- Every server must declare an explicit allow-list of caller identities
  (`identity.AllowList`), which is also what makes the "no agent-to-agent"
  invariant enforceable rather than aspirational.

## Alternatives considered
- Self-hosted username/password auth: rejected — more implementation and
  audit surface for a security-sensitive early-stage product, no clear
  benefit over OIDC delegation.
- Shared API keys for internal services: rejected — a single leaked key
  would grant broad access; short-lived mTLS identities limit blast
  radius and support automatic rotation.
