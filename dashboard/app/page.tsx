"use client";

/**
 * Overview: sprint velocity, agent utilization, open escalations at a
 * glance — the EM's landing page. Only the tasks count is backed by a
 * real RPC today (see gateway/app/routers/tasks.py); the others render
 * an honest "not available yet" tile instead of a fake number.
 */

import { AsyncSection } from "@/components/AsyncSection";
import { AuthGuard } from "@/components/AuthGuard";
import { listAgentSessions, listPendingEscalations, listReadyTasks } from "@/lib/api-client";
import { useAsync } from "@/lib/useAsync";

function TaskStat() {
  const state = useAsync(listReadyTasks, []);
  return (
    <div className="card">
      <div className="stat-label">Ready tasks</div>
      <AsyncSection state={state}>
        {(tasks) => <div className="stat-value">{tasks.length}</div>}
      </AsyncSection>
    </div>
  );
}

function AgentStat() {
  const state = useAsync(listAgentSessions, []);
  return (
    <div className="card">
      <div className="stat-label">Active agent sessions</div>
      <AsyncSection state={state}>
        {(sessions) => <div className="stat-value">{sessions.length}</div>}
      </AsyncSection>
    </div>
  );
}

function EscalationStat() {
  const state = useAsync(listPendingEscalations, []);
  return (
    <div className="card">
      <div className="stat-label">Pending escalations</div>
      <AsyncSection state={state}>
        {(escalations) => <div className="stat-value">{escalations.length}</div>}
      </AsyncSection>
    </div>
  );
}

export default function OverviewPage() {
  return (
    <AuthGuard>
      {(user) => (
        <>
          <h1>Overview</h1>
          <p className="subtitle">
            Signed in as {user.subject} ({user.role}), tenant {user.tenantId}.
          </p>
          <div className="card-grid">
            <TaskStat />
            <AgentStat />
            <EscalationStat />
          </div>
        </>
      )}
    </AuthGuard>
  );
}
