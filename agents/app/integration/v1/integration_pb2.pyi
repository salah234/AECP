import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ConflictKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONFLICT_KIND_UNSPECIFIED: _ClassVar[ConflictKind]
    CONFLICT_KIND_TEXTUAL: _ClassVar[ConflictKind]
    CONFLICT_KIND_SEMANTIC: _ClassVar[ConflictKind]
    CONFLICT_KIND_OWNERSHIP: _ClassVar[ConflictKind]
CONFLICT_KIND_UNSPECIFIED: ConflictKind
CONFLICT_KIND_TEXTUAL: ConflictKind
CONFLICT_KIND_SEMANTIC: ConflictKind
CONFLICT_KIND_OWNERSHIP: ConflictKind

class ConflictReport(_message.Message):
    __slots__ = ("report_id", "tenant_id", "kind", "task_ids", "description", "auto_resolvable", "detected_at")
    REPORT_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    AUTO_RESOLVABLE_FIELD_NUMBER: _ClassVar[int]
    DETECTED_AT_FIELD_NUMBER: _ClassVar[int]
    report_id: str
    tenant_id: str
    kind: ConflictKind
    task_ids: _containers.RepeatedScalarFieldContainer[str]
    description: str
    auto_resolvable: bool
    detected_at: _timestamp_pb2.Timestamp
    def __init__(self, report_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., kind: _Optional[_Union[ConflictKind, str]] = ..., task_ids: _Optional[_Iterable[str]] = ..., description: _Optional[str] = ..., auto_resolvable: _Optional[bool] = ..., detected_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class MergePolicyDecision(_message.Message):
    __slots__ = ("report_id", "auto_merge", "requires_human", "rationale")
    REPORT_ID_FIELD_NUMBER: _ClassVar[int]
    AUTO_MERGE_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_HUMAN_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    report_id: str
    auto_merge: bool
    requires_human: bool
    rationale: str
    def __init__(self, report_id: _Optional[str] = ..., auto_merge: _Optional[bool] = ..., requires_human: _Optional[bool] = ..., rationale: _Optional[str] = ...) -> None: ...

class DetectConflictsRequest(_message.Message):
    __slots__ = ("tenant_id", "candidate_task_ids")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    CANDIDATE_TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    candidate_task_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, tenant_id: _Optional[str] = ..., candidate_task_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class DetectConflictsResponse(_message.Message):
    __slots__ = ("reports",)
    REPORTS_FIELD_NUMBER: _ClassVar[int]
    reports: _containers.RepeatedCompositeFieldContainer[ConflictReport]
    def __init__(self, reports: _Optional[_Iterable[_Union[ConflictReport, _Mapping]]] = ...) -> None: ...

class ResolveMergePolicyRequest(_message.Message):
    __slots__ = ("report_id", "risk_tier")
    REPORT_ID_FIELD_NUMBER: _ClassVar[int]
    RISK_TIER_FIELD_NUMBER: _ClassVar[int]
    report_id: str
    risk_tier: _common_pb2.RiskTier
    def __init__(self, report_id: _Optional[str] = ..., risk_tier: _Optional[_Union[_common_pb2.RiskTier, str]] = ...) -> None: ...

class ResolveMergePolicyResponse(_message.Message):
    __slots__ = ("decision",)
    DECISION_FIELD_NUMBER: _ClassVar[int]
    decision: MergePolicyDecision
    def __init__(self, decision: _Optional[_Union[MergePolicyDecision, _Mapping]] = ...) -> None: ...

class SemanticDiffRequest(_message.Message):
    __slots__ = ("tenant_id", "task_id_a", "task_id_b")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_A_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_B_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    task_id_a: str
    task_id_b: str
    def __init__(self, tenant_id: _Optional[str] = ..., task_id_a: _Optional[str] = ..., task_id_b: _Optional[str] = ...) -> None: ...

class SemanticDiffResponse(_message.Message):
    __slots__ = ("jointly_coherent", "explanation")
    JOINTLY_COHERENT_FIELD_NUMBER: _ClassVar[int]
    EXPLANATION_FIELD_NUMBER: _ClassVar[int]
    jointly_coherent: bool
    explanation: str
    def __init__(self, jointly_coherent: _Optional[bool] = ..., explanation: _Optional[str] = ...) -> None: ...
