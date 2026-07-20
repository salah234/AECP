"use client";

/**
 * Escalation review queue: the primary EM-in-the-loop surface. Pending
 * Tier 2/3 approvals, open conflicts, and drift reports, backed by
 * GET /api/v1/escalations via lib/api-client.ts.
 *
 * CoordinatorService.Escalate only auto-decides a *new* agent-initiated
 * request from risk-tier policy — there is no RPC yet for a human to
 * resolve a task already sitting in ESCALATED state (see
 * gateway/app/routers/escalations.py's docstring), so every section here
 * renders an honest "not available yet" notice today. The approve/reject
 * actions are wired and will work as soon as that RPC exists — nothing
 * else in this page needs to change.
 */

import { useState } from "react";

import { AsyncSection } from "@/components/AsyncSection";
import { AuthGuard } from "@/components/AuthGuard";
import { StatusBadge } from "@/components/StatusBadge";
import { ApiError, approveEscalation, listPendingEscalations, rejectEscalation } from "@/lib/api-client";
import { useAsync } from "@/lib/useAsync";

function EscalationActions({ taskId }: { taskId: string }) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(kind: "approve" | "reject") {
    setBusy(kind);
    setError(null);
    try {
      await (kind === "approve" ? approveEscalation(taskId) : rejectEscalation(taskId));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : `Failed to ${kind}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <button type="button" disabled={busy !== null} onClick={() => act("approve")}>
        {busy === "approve" ? "…" : "Approve"}
      </button>
      <button
        type="button"
        className="danger"
        disabled={busy !== null}
        onClick={() => act("reject")}
      >
        {busy === "reject" ? "…" : "Reject"}
      </button>
      {error && <span className="error-text">{error}</span>}
    </div>
  );
}

export default function EscalationsPage() {
  const state = useAsync(listPendingEscalations, []);

  return (
    <AuthGuard>
      {() => (
        <>
          <h1>Escalations</h1>
          <p className="subtitle">Pending Tier 2/3 approvals requiring a human decision.</p>

          <AsyncSection state={state}>
            {(escalations) =>
              escalations.length === 0 ? (
                <p className="muted">No pending escalations.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Reason</th>
                      <th>Requested tier</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {escalations.map((escalation) => (
                      <tr key={escalation.taskId}>
                        <td>{escalation.taskId}</td>
                        <td>{escalation.reason}</td>
                        <td>
                          <StatusBadge value={escalation.requestedRiskTier} />
                        </td>
                        <td>
                          <EscalationActions taskId={escalation.taskId} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            }
          </AsyncSection>
        </>
      )}
    </AuthGuard>
  );
}
