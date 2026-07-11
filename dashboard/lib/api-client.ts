/**
 * Thin fetch wrapper around the Gateway's REST API. All requests are
 * same-origin-or-configured-origin with credentials included (the
 * session cookie set by gateway/app/auth.py) — no client-held bearer
 * token, no direct calls to internal services.
 */

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

export async function listReadyTasks(): Promise<TaskNode[]> {
  throw new Error("not implemented");
}

export async function listAgentSessions(): Promise<AgentSession[]> {
  throw new Error("not implemented");
}

export async function listDecisions(taskId?: string): Promise<DecisionLogEntry[]> {
  throw new Error("not implemented");
}

export async function listPendingEscalations(): Promise<Escalation[]> {
  throw new Error("not implemented");
}

export async function approveEscalation(taskId: string): Promise<void> {
  throw new Error("not implemented");
}

export async function rejectEscalation(taskId: string): Promise<void> {
  throw new Error("not implemented");
}
