import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RiskTier(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RISK_TIER_UNSPECIFIED: _ClassVar[RiskTier]
    RISK_TIER_MECHANICAL: _ClassVar[RiskTier]
    RISK_TIER_LOCAL: _ClassVar[RiskTier]
    RISK_TIER_STRUCTURAL: _ClassVar[RiskTier]
    RISK_TIER_ARCHITECTURAL: _ClassVar[RiskTier]

class TaskStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_STATUS_UNSPECIFIED: _ClassVar[TaskStatus]
    TASK_STATUS_PENDING: _ClassVar[TaskStatus]
    TASK_STATUS_BLOCKED: _ClassVar[TaskStatus]
    TASK_STATUS_ASSIGNED: _ClassVar[TaskStatus]
    TASK_STATUS_IN_PROGRESS: _ClassVar[TaskStatus]
    TASK_STATUS_IN_REVIEW: _ClassVar[TaskStatus]
    TASK_STATUS_ESCALATED: _ClassVar[TaskStatus]
    TASK_STATUS_DONE: _ClassVar[TaskStatus]
    TASK_STATUS_ABANDONED: _ClassVar[TaskStatus]
RISK_TIER_UNSPECIFIED: RiskTier
RISK_TIER_MECHANICAL: RiskTier
RISK_TIER_LOCAL: RiskTier
RISK_TIER_STRUCTURAL: RiskTier
RISK_TIER_ARCHITECTURAL: RiskTier
TASK_STATUS_UNSPECIFIED: TaskStatus
TASK_STATUS_PENDING: TaskStatus
TASK_STATUS_BLOCKED: TaskStatus
TASK_STATUS_ASSIGNED: TaskStatus
TASK_STATUS_IN_PROGRESS: TaskStatus
TASK_STATUS_IN_REVIEW: TaskStatus
TASK_STATUS_ESCALATED: TaskStatus
TASK_STATUS_DONE: TaskStatus
TASK_STATUS_ABANDONED: TaskStatus

class TenantContext(_message.Message):
    __slots__ = ("tenant_id",)
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    def __init__(self, tenant_id: _Optional[str] = ...) -> None: ...

class OwnershipBoundary(_message.Message):
    __slots__ = ("path_globs", "forbidden_globs")
    PATH_GLOBS_FIELD_NUMBER: _ClassVar[int]
    FORBIDDEN_GLOBS_FIELD_NUMBER: _ClassVar[int]
    path_globs: _containers.RepeatedScalarFieldContainer[str]
    forbidden_globs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, path_globs: _Optional[_Iterable[str]] = ..., forbidden_globs: _Optional[_Iterable[str]] = ...) -> None: ...

class Actor(_message.Message):
    __slots__ = ("kind", "id")
    class Kind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        KIND_UNSPECIFIED: _ClassVar[Actor.Kind]
        KIND_HUMAN: _ClassVar[Actor.Kind]
        KIND_AGENT: _ClassVar[Actor.Kind]
        KIND_COORDINATOR: _ClassVar[Actor.Kind]
    KIND_UNSPECIFIED: Actor.Kind
    KIND_HUMAN: Actor.Kind
    KIND_AGENT: Actor.Kind
    KIND_COORDINATOR: Actor.Kind
    KIND_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    kind: Actor.Kind
    id: str
    def __init__(self, kind: _Optional[_Union[Actor.Kind, str]] = ..., id: _Optional[str] = ...) -> None: ...

class AuditEvent(_message.Message):
    __slots__ = ("event_id", "tenant_id", "actor", "action", "resource", "security_relevant", "occurred_at")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_FIELD_NUMBER: _ClassVar[int]
    SECURITY_RELEVANT_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    tenant_id: str
    actor: Actor
    action: str
    resource: str
    security_relevant: bool
    occurred_at: _timestamp_pb2.Timestamp
    def __init__(self, event_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., actor: _Optional[_Union[Actor, _Mapping]] = ..., action: _Optional[str] = ..., resource: _Optional[str] = ..., security_relevant: _Optional[bool] = ..., occurred_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
