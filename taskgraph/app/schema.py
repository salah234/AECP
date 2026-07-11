"""Pydantic models mirroring proto/taskgraph/v1/taskgraph.proto.

These are the Python-native shapes used inside this service (graph
validation, repository layer); the gRPC layer converts to/from the
generated protobuf messages at the boundary.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class RiskTier(str, Enum):
    MECHANICAL = "mechanical"
    LOCAL = "local"
    STRUCTURAL = "structural"
    ARCHITECTURAL = "architectural"


class TaskStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    ESCALATED = "escalated"
    DONE = "done"
    ABANDONED = "abandoned"


class OwnershipBoundary(BaseModel):
    path_globs: list[str]
    forbidden_globs: list[str] = []


class DefinitionOfDone(BaseModel):
    required_checks: list[str]
    acceptance_criteria: list[str]
    requires_human_review_gate: bool


class TaskNode(BaseModel):
    task_id: str
    tenant_id: str
    title: str
    description: str
    risk_tier: RiskTier
    status: TaskStatus
    ownership: OwnershipBoundary
    depends_on_task_ids: list[str] = []
    blocks_task_ids: list[str] = []
    definition_of_done: DefinitionOfDone
    assigned_agent_id: str | None = None
    created_at: datetime
    updated_at: datetime
