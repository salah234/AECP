# Security Policy

## Reporting a vulnerability

Do not open a public GitHub issue for suspected security vulnerabilities.
Email the maintainers (see repository owner) with a description and
reproduction steps. Target acknowledgement time and disclosure process:
fill in once a real security contact/process is established — do not
publish a placeholder email as if it were monitored.

## Scope

This policy covers AECP's own infrastructure and services (`/coordinator`,
`/taskgraph`, `/agents`, `/state`, `/integration`, `/observability`,
`/gateway`, `/platform`, `/dashboard`) — not the third-party codebases
AECP is coordinating work on, which have their own security posture.

## Supported versions

AECP is pre-1.0. Only the latest `main` branch is supported; there is no
backported patch policy yet.

## Design principles this codebase must uphold

See `/security/THREAT_MODEL.md` for the full trust-boundary breakdown.
The short version, binding on every PR:

- No agent-to-agent network path, ever (enforced in both
  `deploy/k8s/networkpolicy` and `platform/aecp_platform/identity.py`).
- No service trusts a client-supplied tenant id; tenant context is always
  derived server-side from a verified session or service identity.
- No secret is logged, and no production secret is read from a plain
  environment variable (`aecp_platform.secrets.EnvSecretProvider` is
  dev/CI only).
- Every Tier 2+ action and every auth/authz failure is written to the
  append-only audit trail (`observability/app/audit.py`), not just
  application logs.
- Postgres Row-Level Security is mandatory on every tenant-scoped table;
  a migration that adds a tenant-scoped table without an RLS policy is a
  bug, not a follow-up.
