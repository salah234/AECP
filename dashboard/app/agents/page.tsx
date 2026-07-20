"use client";

/**
 * Agent activity view: live sessions and their status, backed by
 * GET /api/v1/agents via lib/api-client.ts. Gateway has no network edge
 * or RPC to Agent Pool today (see gateway/app/routers/agents.py) — this
 * page will show an honest "not available yet" notice until a
 * Coordinator-mediated RPC closes that gap, rather than a fake list.
 */

import { AsyncSection } from "@/components/AsyncSection";
import { AuthGuard } from "@/components/AuthGuard";
import { StatusBadge } from "@/components/StatusBadge";
import { listAgentSessions } from "@/lib/api-client";
import { useAsync } from "@/lib/useAsync";

export default function AgentsPage() {
  const state = useAsync(listAgentSessions, []);

  return (
    <AuthGuard>
      {() => (
        <>
          <h1>Agents</h1>
          <p className="subtitle">Live agent sessions for your tenant.</p>
          <AsyncSection state={state}>
            {(sessions) =>
              sessions.length === 0 ? (
                <p className="muted">No active agent sessions.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Session</th>
                      <th>Task</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((session) => (
                      <tr key={session.sessionId}>
                        <td>{session.sessionId}</td>
                        <td>{session.taskId}</td>
                        <td>
                          <StatusBadge value={session.status} />
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
