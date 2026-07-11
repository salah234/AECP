-- Append-only audit trail. No UPDATE/DELETE grants for application roles
-- in production (see deploy/terraform); this migration only defines shape.

CREATE TABLE audit_events (
    event_id            UUID PRIMARY KEY,
    tenant_id            UUID NOT NULL,
    actor_kind           TEXT NOT NULL CHECK (actor_kind IN ('human', 'agent', 'coordinator')),
    actor_id             TEXT NOT NULL,
    action                TEXT NOT NULL,
    resource              TEXT NOT NULL,
    security_relevant     BOOLEAN NOT NULL DEFAULT false,
    occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_events_tenant_time ON audit_events (tenant_id, occurred_at DESC);
CREATE INDEX idx_audit_events_security_relevant ON audit_events (tenant_id, occurred_at DESC) WHERE security_relevant;

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_audit_events ON audit_events
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

-- REVOKE UPDATE, DELETE from the application role explicitly once the
-- role is created in deploy/terraform, so append-only is enforced by the
-- database, not merely by application code discipline.
