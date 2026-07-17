import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from app.common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AgentSessionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AGENT_SESSION_STATUS_UNSPECIFIED: _ClassVar[AgentSessionStatus]
    AGENT_SESSION_STATUS_HYDRATING: _ClassVar[AgentSessionStatus]
    AGENT_SESSION_STATUS_ACTIVE: _ClassVar[AgentSessionStatus]
    AGENT_SESSION_STATUS_HANDOFF_PENDING: _ClassVar[AgentSessionStatus]
    AGENT_SESSION_STATUS_TERMINATED: _ClassVar[AgentSessionStatus]
    AGENT_SESSION_STATUS_FAILED: _ClassVar[AgentSessionStatus]
AGENT_SESSION_STATUS_UNSPECIFIED: AgentSessionStatus
AGENT_SESSION_STATUS_HYDRATING: AgentSessionStatus
AGENT_SESSION_STATUS_ACTIVE: AgentSessionStatus
AGENT_SESSION_STATUS_HANDOFF_PENDING: AgentSessionStatus
AGENT_SESSION_STATUS_TERMINATED: AgentSessionStatus
AGENT_SESSION_STATUS_FAILED: AgentSessionStatus

class AgentSession(_message.Message):
    __slots__ = ("session_id", "tenant_id", "task_id", "status", "granted_risk_tier", "spawned_at", "expires_at", "ownership", "task_node_snapshot")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    GRANTED_RISK_TIER_FIELD_NUMBER: _ClassVar[int]
    SPAWNED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    OWNERSHIP_FIELD_NUMBER: _ClassVar[int]
    TASK_NODE_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    tenant_id: str
    task_id: str
    status: AgentSessionStatus
    granted_risk_tier: _common_pb2.RiskTier
    spawned_at: _timestamp_pb2.Timestamp
    expires_at: _timestamp_pb2.Timestamp
    ownership: _common_pb2.OwnershipBoundary
    task_node_snapshot: bytes
    def __init__(self, session_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., task_id: _Optional[str] = ..., status: _Optional[_Union[AgentSessionStatus, str]] = ..., granted_risk_tier: _Optional[_Union[_common_pb2.RiskTier, str]] = ..., spawned_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., ownership: _Optional[_Union[_common_pb2.OwnershipBoundary, _Mapping]] = ..., task_node_snapshot: _Optional[bytes] = ...) -> None: ...

class SpawnSessionRequest(_message.Message):
    __slots__ = ("tenant_id", "task_id", "granted_risk_tier", "ownership", "task_node_snapshot")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    GRANTED_RISK_TIER_FIELD_NUMBER: _ClassVar[int]
    OWNERSHIP_FIELD_NUMBER: _ClassVar[int]
    TASK_NODE_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    task_id: str
    granted_risk_tier: _common_pb2.RiskTier
    ownership: _common_pb2.OwnershipBoundary
    task_node_snapshot: bytes
    def __init__(self, tenant_id: _Optional[str] = ..., task_id: _Optional[str] = ..., granted_risk_tier: _Optional[_Union[_common_pb2.RiskTier, str]] = ..., ownership: _Optional[_Union[_common_pb2.OwnershipBoundary, _Mapping]] = ..., task_node_snapshot: _Optional[bytes] = ...) -> None: ...

class SpawnSessionResponse(_message.Message):
    __slots__ = ("session",)
    SESSION_FIELD_NUMBER: _ClassVar[int]
    session: AgentSession
    def __init__(self, session: _Optional[_Union[AgentSession, _Mapping]] = ...) -> None: ...

class HydrateContextRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class ContextBundle(_message.Message):
    __slots__ = ("task_id", "task_node", "ownership_boundary", "relevant_interface_contracts", "relevant_decision_log_entries")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_NODE_FIELD_NUMBER: _ClassVar[int]
    OWNERSHIP_BOUNDARY_FIELD_NUMBER: _ClassVar[int]
    RELEVANT_INTERFACE_CONTRACTS_FIELD_NUMBER: _ClassVar[int]
    RELEVANT_DECISION_LOG_ENTRIES_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    task_node: bytes
    ownership_boundary: bytes
    relevant_interface_contracts: _containers.RepeatedScalarFieldContainer[bytes]
    relevant_decision_log_entries: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, task_id: _Optional[str] = ..., task_node: _Optional[bytes] = ..., ownership_boundary: _Optional[bytes] = ..., relevant_interface_contracts: _Optional[_Iterable[bytes]] = ..., relevant_decision_log_entries: _Optional[_Iterable[bytes]] = ...) -> None: ...

class HydrateContextResponse(_message.Message):
    __slots__ = ("context_bundle", "context_bundle_uri")
    CONTEXT_BUNDLE_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_BUNDLE_URI_FIELD_NUMBER: _ClassVar[int]
    context_bundle: bytes
    context_bundle_uri: str
    def __init__(self, context_bundle: _Optional[bytes] = ..., context_bundle_uri: _Optional[str] = ...) -> None: ...

class HandoffSessionRequest(_message.Message):
    __slots__ = ("session_id", "reason")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    reason: str
    def __init__(self, session_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class HandoffSessionResponse(_message.Message):
    __slots__ = ("new_session",)
    NEW_SESSION_FIELD_NUMBER: _ClassVar[int]
    new_session: AgentSession
    def __init__(self, new_session: _Optional[_Union[AgentSession, _Mapping]] = ...) -> None: ...

class TerminateSessionRequest(_message.Message):
    __slots__ = ("session_id", "reason")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    reason: str
    def __init__(self, session_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class TerminateSessionResponse(_message.Message):
    __slots__ = ("terminated",)
    TERMINATED_FIELD_NUMBER: _ClassVar[int]
    terminated: bool
    def __init__(self, terminated: _Optional[bool] = ...) -> None: ...
