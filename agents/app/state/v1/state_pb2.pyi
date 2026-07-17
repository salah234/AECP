import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from app.common.v1 import common_pb2 as _common_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DecisionLogEntry(_message.Message):
    __slots__ = ("entry_id", "tenant_id", "task_id", "summary", "rationale", "decided_by", "decided_at")
    ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    DECIDED_BY_FIELD_NUMBER: _ClassVar[int]
    DECIDED_AT_FIELD_NUMBER: _ClassVar[int]
    entry_id: str
    tenant_id: str
    task_id: str
    summary: str
    rationale: str
    decided_by: _common_pb2.Actor
    decided_at: _timestamp_pb2.Timestamp
    def __init__(self, entry_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., task_id: _Optional[str] = ..., summary: _Optional[str] = ..., rationale: _Optional[str] = ..., decided_by: _Optional[_Union[_common_pb2.Actor, _Mapping]] = ..., decided_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class OwnershipRecord(_message.Message):
    __slots__ = ("tenant_id", "module_path", "last_task_id", "last_agent_id", "last_touched_at")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    MODULE_PATH_FIELD_NUMBER: _ClassVar[int]
    LAST_TASK_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_AGENT_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_TOUCHED_AT_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    module_path: str
    last_task_id: str
    last_agent_id: str
    last_touched_at: _timestamp_pb2.Timestamp
    def __init__(self, tenant_id: _Optional[str] = ..., module_path: _Optional[str] = ..., last_task_id: _Optional[str] = ..., last_agent_id: _Optional[str] = ..., last_touched_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class InterfaceContract(_message.Message):
    __slots__ = ("contract_id", "tenant_id", "name", "schema", "version", "frozen")
    CONTRACT_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    FROZEN_FIELD_NUMBER: _ClassVar[int]
    contract_id: str
    tenant_id: str
    name: str
    schema: str
    version: int
    frozen: bool
    def __init__(self, contract_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., name: _Optional[str] = ..., schema: _Optional[str] = ..., version: _Optional[int] = ..., frozen: _Optional[bool] = ...) -> None: ...

class DriftReport(_message.Message):
    __slots__ = ("report_id", "tenant_id", "contract_id", "description", "resolved", "detected_at")
    REPORT_ID_FIELD_NUMBER: _ClassVar[int]
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_ID_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    RESOLVED_FIELD_NUMBER: _ClassVar[int]
    DETECTED_AT_FIELD_NUMBER: _ClassVar[int]
    report_id: str
    tenant_id: str
    contract_id: str
    description: str
    resolved: bool
    detected_at: _timestamp_pb2.Timestamp
    def __init__(self, report_id: _Optional[str] = ..., tenant_id: _Optional[str] = ..., contract_id: _Optional[str] = ..., description: _Optional[str] = ..., resolved: _Optional[bool] = ..., detected_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class RecordDecisionRequest(_message.Message):
    __slots__ = ("entry",)
    ENTRY_FIELD_NUMBER: _ClassVar[int]
    entry: DecisionLogEntry
    def __init__(self, entry: _Optional[_Union[DecisionLogEntry, _Mapping]] = ...) -> None: ...

class RecordDecisionResponse(_message.Message):
    __slots__ = ("entry",)
    ENTRY_FIELD_NUMBER: _ClassVar[int]
    entry: DecisionLogEntry
    def __init__(self, entry: _Optional[_Union[DecisionLogEntry, _Mapping]] = ...) -> None: ...

class GetOwnershipRequest(_message.Message):
    __slots__ = ("tenant_id", "module_path")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    MODULE_PATH_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    module_path: str
    def __init__(self, tenant_id: _Optional[str] = ..., module_path: _Optional[str] = ...) -> None: ...

class GetOwnershipResponse(_message.Message):
    __slots__ = ("record",)
    RECORD_FIELD_NUMBER: _ClassVar[int]
    record: OwnershipRecord
    def __init__(self, record: _Optional[_Union[OwnershipRecord, _Mapping]] = ...) -> None: ...

class GetInterfaceContractRequest(_message.Message):
    __slots__ = ("contract_id",)
    CONTRACT_ID_FIELD_NUMBER: _ClassVar[int]
    contract_id: str
    def __init__(self, contract_id: _Optional[str] = ...) -> None: ...

class GetInterfaceContractResponse(_message.Message):
    __slots__ = ("contract",)
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    contract: InterfaceContract
    def __init__(self, contract: _Optional[_Union[InterfaceContract, _Mapping]] = ...) -> None: ...

class ReportDriftRequest(_message.Message):
    __slots__ = ("report",)
    REPORT_FIELD_NUMBER: _ClassVar[int]
    report: DriftReport
    def __init__(self, report: _Optional[_Union[DriftReport, _Mapping]] = ...) -> None: ...

class ReportDriftResponse(_message.Message):
    __slots__ = ("report",)
    REPORT_FIELD_NUMBER: _ClassVar[int]
    report: DriftReport
    def __init__(self, report: _Optional[_Union[DriftReport, _Mapping]] = ...) -> None: ...
