import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from common.v1 import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RecordAuditEventRequest(_message.Message):
    __slots__ = ("event",)
    EVENT_FIELD_NUMBER: _ClassVar[int]
    event: _common_pb2.AuditEvent
    def __init__(self, event: _Optional[_Union[_common_pb2.AuditEvent, _Mapping]] = ...) -> None: ...

class RecordAuditEventResponse(_message.Message):
    __slots__ = ("event_id",)
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    def __init__(self, event_id: _Optional[str] = ...) -> None: ...

class QueryAuditEventsRequest(_message.Message):
    __slots__ = ("tenant_id", "since", "security_relevant_only")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    SINCE_FIELD_NUMBER: _ClassVar[int]
    SECURITY_RELEVANT_ONLY_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    since: _timestamp_pb2.Timestamp
    security_relevant_only: bool
    def __init__(self, tenant_id: _Optional[str] = ..., since: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., security_relevant_only: _Optional[bool] = ...) -> None: ...

class QueryAuditEventsResponse(_message.Message):
    __slots__ = ("events",)
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[_common_pb2.AuditEvent]
    def __init__(self, events: _Optional[_Iterable[_Union[_common_pb2.AuditEvent, _Mapping]]] = ...) -> None: ...
