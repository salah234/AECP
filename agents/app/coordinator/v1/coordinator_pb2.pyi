from google.protobuf import timestamp_pb2 as _timestamp_pb2
from app.common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AssignmentRequest(_message.Message):
    __slots__ = ("task_id", "tenant_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    tenant_id: str
    def __init__(self, task_id: _Optional[str] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class AssignmentDecision(_message.Message):
    __slots__ = ("task_id", "agent_id", "granted_risk_tier", "rationale")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    GRANTED_RISK_TIER_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    agent_id: str
    granted_risk_tier: _common_pb2.RiskTier
    rationale: str
    def __init__(self, task_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., granted_risk_tier: _Optional[_Union[_common_pb2.RiskTier, str]] = ..., rationale: _Optional[str] = ...) -> None: ...

class ScheduleRequest(_message.Message):
    __slots__ = ("tenant_id",)
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    def __init__(self, tenant_id: _Optional[str] = ...) -> None: ...

class ScheduleResponse(_message.Message):
    __slots__ = ("decisions",)
    DECISIONS_FIELD_NUMBER: _ClassVar[int]
    decisions: _containers.RepeatedCompositeFieldContainer[AssignmentDecision]
    def __init__(self, decisions: _Optional[_Iterable[_Union[AssignmentDecision, _Mapping]]] = ...) -> None: ...

class EscalateRequest(_message.Message):
    __slots__ = ("task_id", "agent_id", "reason", "requested_risk_tier", "tenant_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    REQUESTED_RISK_TIER_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    agent_id: str
    reason: str
    requested_risk_tier: _common_pb2.RiskTier
    tenant_id: str
    def __init__(self, task_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., reason: _Optional[str] = ..., requested_risk_tier: _Optional[_Union[_common_pb2.RiskTier, str]] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class EscalateResponse(_message.Message):
    __slots__ = ("approved", "decided_by")
    APPROVED_FIELD_NUMBER: _ClassVar[int]
    DECIDED_BY_FIELD_NUMBER: _ClassVar[int]
    approved: bool
    decided_by: str
    def __init__(self, approved: _Optional[bool] = ..., decided_by: _Optional[str] = ...) -> None: ...

class ReportBlockerRequest(_message.Message):
    __slots__ = ("task_id", "agent_id", "description", "tenant_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    agent_id: str
    description: str
    tenant_id: str
    def __init__(self, task_id: _Optional[str] = ..., agent_id: _Optional[str] = ..., description: _Optional[str] = ..., tenant_id: _Optional[str] = ...) -> None: ...

class ReportBlockerResponse(_message.Message):
    __slots__ = ("acknowledged",)
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    def __init__(self, acknowledged: _Optional[bool] = ...) -> None: ...
