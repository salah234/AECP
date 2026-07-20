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
import { ApiError, createTask, listReadyTasks, updateTaskStatus, type TaskNode } from "@/lib/api-client";
import { useAsync } from "@/lib/useAsync";

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
