"""Proto <-> REST field/enum conversion shared by app/routers/*.

Kept as plain functions rather than a duplicate set of pydantic models
mirroring every proto message: the wire types are already typed schemas
(see /proto), and the dashboard's own lib/api-client.ts documents exactly
which camelCase fields it reads — these helpers produce just those.
"""

from __future__ import annotations

from app.agents.v1 import agents_pb2
from app.common.v1 import common_pb2
from app.coordinator.v1 import coordinator_pb2
from app.state.v1 import state_pb2
from app.taskgraph.v1 import taskgraph_pb2


def risk_tier_to_str(value: int) -> str:
    return common_pb2.RiskTier.Name(value).removeprefix("RISK_TIER_").lower()


def risk_tier_from_str(value: str) -> int:
    try:
        return common_pb2.RiskTier.Value(f"RISK_TIER_{value.upper()}")
    except ValueError as exc:
        raise ValueError(f"Unknown risk_tier '{value}'") from exc


def task_status_to_str(value: int) -> str:
    return common_pb2.TaskStatus.Name(value).removeprefix("TASK_STATUS_").lower()


def task_status_from_str(value: str) -> int:
    try:
        return common_pb2.TaskStatus.Value(f"TASK_STATUS_{value.upper()}")
    except ValueError as exc:
        raise ValueError(f"Unknown status '{value}'") from exc


def task_node_to_dict(node: "taskgraph_pb2.TaskNode") -> dict:
    return {
        "taskId": node.task_id,
        "title": node.title,
        "description": node.description,
        "status": task_status_to_str(node.status),
        "riskTier": risk_tier_to_str(node.risk_tier),
        "dependsOnTaskIds": list(node.depends_on_task_ids),
        "blocksTaskIds": list(node.blocks_task_ids),
        "assignedAgentId": node.assigned_agent_id,
    }


def decision_log_entry_to_dict(entry: "state_pb2.DecisionLogEntry") -> dict:
    return {
        "entryId": entry.entry_id,
        "taskId": entry.task_id,
        "summary": entry.summary,
        "rationale": entry.rationale,
        "decidedByKind": common_pb2.Actor.Kind.Name(entry.decided_by.kind),
        "decidedById": entry.decided_by.id,
    }


def agent_session_status_to_str(value: int) -> str:
    return agents_pb2.AgentSessionStatus.Name(value).removeprefix("AGENT_SESSION_STATUS_").lower()


def agent_session_to_dict(session: "agents_pb2.AgentSession") -> dict:
    return {
        "sessionId": session.session_id,
        "taskId": session.task_id,
        "status": agent_session_status_to_str(session.status),
    }


def assignment_decision_to_dict(decision: "coordinator_pb2.AssignmentDecision") -> dict:
    return {
        "taskId": decision.task_id,
        "agentId": decision.agent_id,
        "grantedRiskTier": risk_tier_to_str(decision.granted_risk_tier),
        "rationale": decision.rationale,
    }


def interface_contract_to_dict(contract: "state_pb2.InterfaceContract") -> dict:
    return {
        "contractId": contract.contract_id,
        "name": contract.name,
        "schema": contract.schema,
        "version": contract.version,
        "frozen": contract.frozen,
    }
