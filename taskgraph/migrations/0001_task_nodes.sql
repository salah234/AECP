-- Task Graph schema. tenant_id + Row-Level Security enforce isolation at
-- the database layer as a second line of defense behind
-- aecp_platform.dbtenant (see /security/THREAT_MODEL.md).

CREATE TABLE task_nodes (
    task_id                     UUID PRIMARY KEY,
    tenant_id                   UUID NOT NULL,
    title                       TEXT NOT NULL,
    description                 TEXT NOT NULL DEFAULT '',
    risk_tier                   TEXT NOT NULL CHECK (risk_tier IN ('mechanical', 'local', 'structural', 'architectural')),
    status                      TEXT NOT NULL CHECK (status IN ('pending', 'blocked', 'assigned', 'in_progress', 'in_review', 'escalated', 'done', 'abandoned')),
    ownership_path_globs        TEXT[] NOT NULL DEFAULT '{}',
    ownership_forbidden_globs   TEXT[] NOT NULL DEFAULT '{}',
    definition_of_done          JSONB NOT NULL,
    assigned_agent_id           UUID,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE task_dependencies (
    task_id             UUID NOT NULL REFERENCES task_nodes(task_id) ON DELETE CASCADE,
    depends_on_task_id  UUID NOT NULL REFERENCES task_nodes(task_id) ON DELETE CASCADE,
    tenant_id           UUID NOT NULL,
    PRIMARY KEY (task_id, depends_on_task_id)
);

CREATE INDEX idx_task_nodes_tenant_status ON task_nodes (tenant_id, status);
CREATE INDEX idx_task_dependencies_tenant ON task_dependencies (tenant_id);

ALTER TABLE task_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_nodes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_task_nodes ON task_nodes
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE task_dependencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_dependencies FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_task_dependencies ON task_dependencies
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
