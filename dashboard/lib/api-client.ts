/**
 * Thin fetch wrapper around the Gateway's REST API. All requests are
 * same-origin-or-configured-origin with credentials included (the
 * session cookie set by gateway/app/auth.py) — no client-held bearer
 * token, no direct calls to internal services.
 */

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "";
const JAEGER_URL = process.env.NEXT_PUBLIC_JAEGER_URL ?? "http://localhost:16686";

export interface TaskNode {
  taskId: string;
  title: string;
  status: string;
  riskTier: string;
}

export interface AgentSession {
  sessionId: string;
  taskId: string;
  status: string;
}

export interface DecisionLogEntry {
  entryId: string;
  taskId: string;
  summary: string;
  rationale: string;
}

export interface Escalation {
  taskId: string;
  agentId: string;
  reason: string;
  requestedRiskTier: string;
}

export interface InterfaceContract {
  contractId: string;
  name: string;
  schema: string;
  version: number;
  frozen: boolean;
}

export interface CreateTaskInput {
  title: string;
  description?: string;
  riskTier: string;
  pathGlobs?: string[];
}

export interface AssignmentDecision {
  taskId: string;
  agentId: string;
  grantedRiskTier: string;
  rationale: string;
}

export interface ScheduleResult {
  decisions: AssignmentDecision[];
  traceId: string;
}

/**
 * Raised for any non-2xx Gateway response. `status` lets callers
 * distinguish "this endpoint isn't wired up yet" (501 — see
 * gateway/app/routers/{agents,decisions,escalations}.py, which return a
 * deliberate 501 naming the missing upstream RPC rather than a fake empty
 * list) from a real failure (401/403/5xx), so pages can render an honest
 * "not available yet" state instead of a generic error.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`Gateway request failed (${status}): ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${GATEWAY_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        detail = body.detail;
      }
    } catch {
      // Non-JSON error body — fall back to statusText.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function listReadyTasks(): Promise<TaskNode[]> {
  return request<TaskNode[]>("/api/v1/tasks");
}

/**
 * Beyond the original read-only contract this module started with:
 * gateway's tasks router fully supports create + status update (the only
 * router with a complete backing RPC end to end), so the Tasks page uses
 * these to be a real, working view rather than list-only.
 */
export async function createTask(input: CreateTaskInput): Promise<TaskNode> {
  return request<TaskNode>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify({
      title: input.title,
      description: input.description ?? "",
      risk_tier: input.riskTier,
      path_globs: input.pathGlobs ?? [],
    }),
  });
}

export async function updateTaskStatus(
  taskId: string,
  status: string,
  reason = "",
): Promise<TaskNode> {
  return request<TaskNode>(`/api/v1/tasks/${encodeURIComponent(taskId)}/status`, {
    method: "POST",
    body: JSON.stringify({ status, reason }),
  });
}

export async function getTask(taskId: string): Promise<TaskNode> {
  return request<TaskNode>(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
}

/**
 * Triggers Coordinator.Schedule for the caller's tenant (invokes an agent
 * onto whatever ready task nodes exist) — see gateway/app/routers's
 * coordinator schedule proxy. Returns the resulting assignment decisions
 * plus the OTel trace id of this invocation for jaegerTraceUrl().
 */
export async function scheduleReadyWork(): Promise<ScheduleResult> {
  return request<ScheduleResult>("/api/v1/coordinator/schedule", { method: "POST" });
}

/**
 * Builds a Jaeger UI deep link for a trace id returned by
 * scheduleReadyWork(). Callers should check for an empty traceId
 * themselves (tracing unavailable for that request) rather than linking
 * to a trace that doesn't exist.
 */
export function jaegerTraceUrl(traceId: string): string {
  return `${JAEGER_URL}/trace/${traceId}`;
}

export async function getInterfaceContract(contractId: string): Promise<InterfaceContract> {
  return request<InterfaceContract>(
    `/api/v1/decisions/contracts/${encodeURIComponent(contractId)}`,
  );
}

export async function listAgentSessions(): Promise<AgentSession[]> {
  return request<AgentSession[]>("/api/v1/agents");
}

export async function listDecisions(taskId?: string): Promise<DecisionLogEntry[]> {
  const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
  return request<DecisionLogEntry[]>(`/api/v1/decisions${query}`);
}

export async function listPendingEscalations(): Promise<Escalation[]> {
  return request<Escalation[]>("/api/v1/escalations");
}

export async function approveEscalation(taskId: string): Promise<void> {
  await request<void>(`/api/v1/escalations/${encodeURIComponent(taskId)}/approve`, {
    method: "POST",
  });
}

export async function rejectEscalation(taskId: string): Promise<void> {
  await request<void>(`/api/v1/escalations/${encodeURIComponent(taskId)}/reject`, {
    method: "POST",
  });
}
