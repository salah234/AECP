-- State & Memory Layer schema: decision log (append-only), ownership map,
-- interface contracts, drift reports. tenant_id + RLS on every table.

CREATE TABLE decision_log_entries (
    entry_id                UUID PRIMARY KEY,
    tenant_id                UUID NOT NULL,
    task_id                  UUID NOT NULL,
    summary                  TEXT NOT NULL,
    rationale                TEXT NOT NULL,
    decided_by_kind          TEXT NOT NULL CHECK (decided_by_kind IN ('human', 'agent', 'coordinator')),
    decided_by_id             TEXT NOT NULL,
    supersedes_entry_id      UUID REFERENCES decision_log_entries(entry_id),
    decided_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Append-only: no UPDATE/DELETE grants for application roles (see
-- deploy/terraform for the least-privilege role definitions).

CREATE TABLE ownership_records (
    tenant_id            UUID NOT NULL,
    module_path          TEXT NOT NULL,
    last_task_id         UUID NOT NULL,
    last_agent_id        UUID NOT NULL,
    last_touched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, module_path)
);

CREATE TABLE interface_contracts (
    contract_id       UUID NOT NULL,
    tenant_id         UUID NOT NULL,
    name              TEXT NOT NULL,
    schema_definition TEXT NOT NULL,
    version           INT NOT NULL,
    frozen            BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (contract_id, version)
);

CREATE TABLE drift_reports (
    report_id      UUID PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    contract_id    UUID NOT NULL,
    description    TEXT NOT NULL,
    resolved       BOOLEAN NOT NULL DEFAULT false,
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_decision_log_tenant_task ON decision_log_entries (tenant_id, task_id);
CREATE INDEX idx_drift_reports_tenant_unresolved ON drift_reports (tenant_id) WHERE NOT resolved;

ALTER TABLE decision_log_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE decision_log_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_decision_log ON decision_log_entries
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE ownership_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE ownership_records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_ownership_records ON ownership_records
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE interface_contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE interface_contracts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_interface_contracts ON interface_contracts
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE drift_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE drift_reports FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_drift_reports ON drift_reports
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
