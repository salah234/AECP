/**
 * Small colored label for a task/agent/risk-tier status string. Status
 * vocabulary is whatever the Gateway/TaskGraph enums serialize to (see
 * gateway/app/schemas.py's task_status_to_str/risk_tier_to_str) —
 * unrecognized values still render, just without a specific color, so a
 * future enum value never breaks the UI.
 */

const TONE_BY_STATUS: Record<string, string> = {
  pending: "tone-neutral",
  blocked: "tone-danger",
  assigned: "tone-info",
  in_progress: "tone-info",
  in_review: "tone-warning",
  escalated: "tone-warning",
  done: "tone-success",
  abandoned: "tone-danger",
  active: "tone-success",
  hydrating: "tone-info",
  handoff_pending: "tone-warning",
  terminated: "tone-neutral",
  failed: "tone-danger",
  mechanical: "tone-success",
  local: "tone-info",
  structural: "tone-warning",
  architectural: "tone-danger",
};

export function StatusBadge({ value }: { value: string }) {
  const tone = TONE_BY_STATUS[value.toLowerCase()] ?? "tone-neutral";
  return <span className={`badge ${tone}`}>{value.replace(/_/g, " ")}</span>;
}
