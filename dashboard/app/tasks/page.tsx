"use client";

/**
 * Task graph view: ready/blocked/in-progress nodes for the current
 * tenant, backed by GET /api/v1/tasks via lib/api-client.ts. This is the
 * one page with a fully working backend end to end (TaskGraphService has
 * every RPC this needs), so it also supports creating a task and
 * updating status, not just listing.
 */

import { useState } from "react";

import { AsyncSection } from "@/components/AsyncSection";
import { AuthGuard } from "@/components/AuthGuard";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ApiError,
  createTask,
  getTask,
  jaegerTraceUrl,
  listAgentSessions,
  listReadyTasks,
  scheduleReadyWork,
  updateTaskStatus,
  type AssignmentDecision,
  type TaskNode,
} from "@/lib/api-client";
import { useAsync, usePolledAsync } from "@/lib/useAsync";

// "blocked" counts as terminal for tracking purposes even though a human
// can later move a task out of it (see StatusUpdater below): once an
// invocation's agent session self-reports a blocker it tears itself
// down, so there is nothing left for this row's polling to observe.
const TERMINAL_TASK_STATUSES = ["done", "abandoned", "blocked"];
const POLL_INTERVAL_MS = 2000;

const RISK_TIERS = ["mechanical", "local", "structural", "architectural"];
const STATUSES = [
  "pending",
  "blocked",
  "assigned",
  "in_progress",
  "in_review",
  "escalated",
  "done",
  "abandoned",
];

function CreateTaskForm({ onCreated }: { onCreated: (task: TaskNode) => void }) {
  const [title, setTitle] = useState("");
  const [riskTier, setRiskTier] = useState("local");
  const [pathGlobs, setPathGlobs] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const task = await createTask({
        title,
        riskTier,
        pathGlobs: pathGlobs
          .split(",")
          .map((glob) => glob.trim())
          .filter(Boolean),
      });
      onCreated(task);
      setTitle("");
      setPathGlobs("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="inline-form card" onSubmit={handleSubmit}>
      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>
      <label>
        Risk tier
        <select value={riskTier} onChange={(e) => setRiskTier(e.target.value)}>
          {RISK_TIERS.map((tier) => (
            <option key={tier} value={tier}>
              {tier}
            </option>
          ))}
        </select>
      </label>
      <label>
        Ownership path globs (comma-separated)
        <input
          value={pathGlobs}
          onChange={(e) => setPathGlobs(e.target.value)}
          placeholder="services/billing/**"
        />
      </label>
      <button type="submit" disabled={submitting}>
        {submitting ? "Creating…" : "Create task"}
      </button>
      {error && <span className="error-text">{error}</span>}
    </form>
  );
}

function StatusUpdater({
  task,
  onUpdated,
}: {
  task: TaskNode;
  onUpdated: (task: TaskNode) => void;
}) {
  const [status, setStatus] = useState(task.status);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpdate() {
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateTaskStatus(task.taskId, status, "Updated from dashboard");
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to update status");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      <button className="secondary" type="button" disabled={submitting} onClick={handleUpdate}>
        {submitting ? "…" : "Update"}
      </button>
      {error && <span className="error-text">{error}</span>}
    </div>
  );
}

function TrackedDecisionRow({ decision }: { decision: AssignmentDecision }) {
  const taskState = usePolledAsync(
    () => getTask(decision.taskId),
    {
      pollIntervalMs: POLL_INTERVAL_MS,
      stopWhen: (task) => TERMINAL_TASK_STATUSES.includes(task.status),
    },
    [decision.taskId],
  );

  const sessionsState = usePolledAsync(
    () => listAgentSessions(),
    {
      pollIntervalMs: POLL_INTERVAL_MS,
      stopWhen: () => taskState.status === "success" && TERMINAL_TASK_STATUSES.includes(taskState.data.status),
    },
    [decision.taskId],
  );

  const session =
    sessionsState.status === "success"
      ? sessionsState.data.find((s) => s.taskId === decision.taskId)
      : undefined;

  return (
    <tr>
      <td>{decision.taskId}</td>
      <td>{decision.agentId}</td>
      <td>
        <StatusBadge value={decision.grantedRiskTier} />
      </td>
      <td>{decision.rationale}</td>
      <td>{taskState.status === "success" ? <StatusBadge value={taskState.data.status} /> : "…"}</td>
      <td>
        {sessionsState.status !== "success" ? (
          "…"
        ) : session ? (
          <StatusBadge value={session.status} />
        ) : (
          <span className="muted">no active session</span>
        )}
      </td>
    </tr>
  );
}

function InvokeAgentSection() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ decisions: AssignmentDecision[]; traceId: string } | null>(
    null,
  );

  async function handleSchedule() {
    setSubmitting(true);
    setError(null);
    try {
      const scheduled = await scheduleReadyWork();
      setResult(scheduled);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to schedule ready work");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <h2>Invoke an agent</h2>
      <p className="subtitle">
        Schedules every ready task node for your tenant onto an available agent.
      </p>
      <div className="inline-form card">
        <button type="button" disabled={submitting} onClick={handleSchedule}>
          {submitting ? "Scheduling…" : "Schedule ready work"}
        </button>
        {error && <span className="error-text">{error}</span>}
      </div>

      {result && (
        <>
          {result.traceId ? (
            <p className="muted">
              Trace:{" "}
              <a href={jaegerTraceUrl(result.traceId)} target="_blank" rel="noreferrer">
                {result.traceId}
              </a>
            </p>
          ) : (
            <p className="muted">Trace not available for this invocation.</p>
          )}

          {result.decisions.length === 0 ? (
            <p className="muted">No ready tasks were assigned.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Agent</th>
                  <th>Granted risk tier</th>
                  <th>Rationale</th>
                  <th>Task status (live)</th>
                  <th>Agent status (live)</th>
                </tr>
              </thead>
              <tbody>
                {result.decisions.map((decision) => (
                  <TrackedDecisionRow key={decision.taskId} decision={decision} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </>
  );
}

export default function TasksPage() {
  const [overrides, setOverrides] = useState<Record<string, TaskNode>>({});
  const state = useAsync(listReadyTasks, []);

  function applyOverride(task: TaskNode) {
    setOverrides((prev) => ({ ...prev, [task.taskId]: task }));
  }

  return (
    <AuthGuard>
      {() => (
        <>
          <h1>Tasks</h1>
          <p className="subtitle">Ready task nodes for your tenant.</p>

          <h2>Create a task</h2>
          <CreateTaskForm onCreated={applyOverride} />

          <InvokeAgentSection />

          <h2>Ready tasks</h2>
          <AsyncSection state={state}>
            {(tasks) => {
              const merged = tasks.map((task) => overrides[task.taskId] ?? task);
              const created = Object.values(overrides).filter(
                (task) => !tasks.some((t) => t.taskId === task.taskId),
              );
              const rows = [...merged, ...created];

              if (rows.length === 0) {
                return <p className="muted">No ready tasks right now.</p>;
              }

              return (
                <table>
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Status</th>
                      <th>Risk tier</th>
                      <th>Update status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((task) => (
                      <tr key={task.taskId}>
                        <td>{task.title}</td>
                        <td>
                          <StatusBadge value={task.status} />
                        </td>
                        <td>
                          <StatusBadge value={task.riskTier} />
                        </td>
                        <td>
                          <StatusUpdater task={task} onUpdated={applyOverride} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              );
            }}
          </AsyncSection>
        </>
      )}
    </AuthGuard>
  );
}
