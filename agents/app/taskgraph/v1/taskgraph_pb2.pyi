import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TaskNode(_message.Message):
    __slots__ = ("task_id", "tenant_id", "title", "description", "risk_tier", "status", "ownership", "depends_on_task_ids", "blocks_task_ids", "definition_of_done", "assigned_agent_id", "created_at", "updated_at")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    RISK_TIER_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    OWNERSHIP_FIELD_NUMBER: _ClassVar[int]
    DEPENDS_ON_TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    BLOCKS_TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    DEFINITION_OF_DONE_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    tenant_id: str
    title: str
    description: str
    risk_tier: _common_pb2.RiskTier
    status: _common_pb2.TaskStatus
    ownership: _common_pb2.OwnershipBoundary
    depends_on_task_ids: _containers.RepeatedScalarFieldContainer[str]
    blocks_task_ids: _containers.RepeatedScalarFieldContainer[str]
    definition_of_done: DefinitionOfDone
    assigned_agent_id: str
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, task_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., risk_tier: _Optional[_Union[_common_pb2.RiskTier, str]] = ..., status: _Optional[_Union[_common_pb2.TaskStatus, str]] = ..., ownership: _Optional[_Union[_common_pb2.OwnershipBoundary, _Mapping]] = ..., depends_on_task_ids: _Optional[_Iterable[str]] = ..., blocks_task_ids: _Optional[_Iterable[str]] = ..., definition_of_done: _Optional[_Union[DefinitionOfDone, _Mapping]] = ..., assigned_agent_id: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class DefinitionOfDone(_message.Message):
    __slots__ = ("required_checks", "acceptance_criteria", "requires_human_review_gate")
    REQUIRED_CHECKS_FIELD_NUMBER: _ClassVar[int]
    ACCEPTANCE_CRITERIA_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_HUMAN_REVIEW_GATE_FIELD_NUMBER: _ClassVar[int]
    required_checks: _containers.RepeatedScalarFieldContainer[str]
    acceptance_criteria: _containers.RepeatedScalarFieldContainer[str]
    requires_human_review_gate: bool
    def __init__(self, required_checks: _Optional[_Iterable[str]] = ..., acceptance_criteria: _Optional[_Iterable[str]] = ..., requires_human_review_gate: _Optional[bool] = ...) -> None: ...

class CreateTaskNodeRequest(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: TaskNode
    def __init__(self, node: _Optional[_Union[TaskNode, _Mapping]] = ...) -> None: ...

class CreateTaskNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: TaskNode
    def __init__(self, node: _Optional[_Union[TaskNode, _Mapping]] = ...) -> None: ...

class GetTaskNodeRequest(_message.Message):
    __slots__ = ("task_id", "tenant_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    tenant_id: str
    def __init__(self, task_id: _Optional[str] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class GetTaskNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: TaskNode
    def __init__(self, node: _Optional[_Union[TaskNode, _Mapping]] = ...) -> None: ...

class UpdateTaskStatusRequest(_message.Message):
    __slots__ = ("task_id", "status", "reason", "tenant_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    status: _common_pb2.TaskStatus
    reason: str
    tenant_id: str
    def __init__(self, task_id: _Optional[str] = ..., status: _Optional[_Union[_common_pb2.TaskStatus, str]] = ..., reason: _Optional[str] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class UpdateTaskStatusResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: TaskNode
    def __init__(self, node: _Optional[_Union[TaskNode, _Mapping]] = ...) -> None: ...

class ListReadyTaskNodesRequest(_message.Message):
    __slots__ = ("tenant_id",)
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    def __init__(self, tenant_id: _Optional[str] = ...) -> None: ...

class ListReadyTaskNodesResponse(_message.Message):
    __slots__ = ("nodes",)
    NODES_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[TaskNode]
    def __init__(self, nodes: _Optional[_Iterable[_Union[TaskNode, _Mapping]]] = ...) -> None: ...

class ValidateOwnershipRequest(_message.Message):
    __slots__ = ("task_id", "changed_paths", "tenant_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    CHANGED_PATHS_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    changed_paths: _containers.RepeatedScalarFieldContainer[str]
    tenant_id: str
    def __init__(self, task_id: _Optional[str] = ..., changed_paths: _Optional[_Iterable[str]] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class ValidateOwnershipResponse(_message.Message):
    __slots__ = ("within_boundary", "violating_paths")
    WITHIN_BOUNDARY_FIELD_NUMBER: _ClassVar[int]
    VIOLATING_PATHS_FIELD_NUMBER: _ClassVar[int]
    within_boundary: bool
    violating_paths: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, within_boundary: _Optional[bool] = ..., violating_paths: _Optional[_Iterable[str]] = ...) -> None: ...
