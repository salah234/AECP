# 0004 — Postgres Row-Level Security for multi-tenancy

## Context
AECP is multi-tenant: one customer's task graph, decision log, and agent
output must never be visible to another tenant, even under an
application bug in one of six services.

## Decision
Every tenant-scoped table carries a `NOT NULL tenant_id` column with a
`FORCE ROW LEVEL SECURITY` policy keyed off a `SET LOCAL app.tenant_id`
session variable. Application code never queries with a raw connection —
it goes through `platform/aecp_platform/dbtenant.TenantScopedPool`, which
is the only thing allowed to set that session variable, and does so from
a server-derived tenant (session claim or verified service identity),
never a client-supplied field.

## Consequences
- Isolation is enforced twice: once by application code scoping its
  queries, once by the database refusing to return rows outside the
  session's tenant even if application code forgets. A bug in one layer
  does not become a cross-tenant leak.
- Every migration that adds a tenant-scoped table must add its RLS
  policy in the same migration — reviewers should treat a missing policy
  as equivalent to a missing `NOT NULL` constraint on a primary key.

## Alternatives considered
- Schema-per-tenant: rejected for this stage — migration fan-out across
  potentially thousands of tenant schemas is an operational burden not
  justified yet; revisit if a single large tenant needs physical
  isolation.
- Database-per-tenant: rejected for the same reason, reconsider for an
  enterprise/dedicated tier later.
