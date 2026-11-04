from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Phase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PHASE_UNSPECIFIED: _ClassVar[Phase]
    PHASE_PREPARING: _ClassVar[Phase]
    PHASE_CSP: _ClassVar[Phase]
    PHASE_ANNEALING: _ClassVar[Phase]
    PHASE_SAVING: _ClassVar[Phase]
    PHASE_DONE: _ClassVar[Phase]

class Weekday(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WEEKDAY_UNSPECIFIED: _ClassVar[Weekday]
    WEEKDAY_LUNES: _ClassVar[Weekday]
    WEEKDAY_MARTES: _ClassVar[Weekday]
    WEEKDAY_MIERCOLES: _ClassVar[Weekday]
    WEEKDAY_JUEVES: _ClassVar[Weekday]
    WEEKDAY_VIERNES: _ClassVar[Weekday]
PHASE_UNSPECIFIED: Phase
PHASE_PREPARING: Phase
PHASE_CSP: Phase
PHASE_ANNEALING: Phase
PHASE_SAVING: Phase
PHASE_DONE: Phase
WEEKDAY_UNSPECIFIED: Weekday
WEEKDAY_LUNES: Weekday
WEEKDAY_MARTES: Weekday
WEEKDAY_MIERCOLES: Weekday
WEEKDAY_JUEVES: Weekday
WEEKDAY_VIERNES: Weekday

class GenerateScheduleRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GenerationEvent(_message.Message):
    __slots__ = ("phase", "message", "subjects_placed", "total_subjects", "iterations", "idle_hours", "idle_hours_before", "improvements", "elapsed_seconds", "total_blocks")
    PHASE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SUBJECTS_PLACED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SUBJECTS_FIELD_NUMBER: _ClassVar[int]
    ITERATIONS_FIELD_NUMBER: _ClassVar[int]
    IDLE_HOURS_FIELD_NUMBER: _ClassVar[int]
    IDLE_HOURS_BEFORE_FIELD_NUMBER: _ClassVar[int]
    IMPROVEMENTS_FIELD_NUMBER: _ClassVar[int]
    ELAPSED_SECONDS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_BLOCKS_FIELD_NUMBER: _ClassVar[int]
    phase: Phase
    message: str
    subjects_placed: int
    total_subjects: int
    iterations: int
    idle_hours: int
    idle_hours_before: int
    improvements: int
    elapsed_seconds: float
    total_blocks: int
    def __init__(self, phase: _Optional[_Union[Phase, str]] = ..., message: _Optional[str] = ..., subjects_placed: _Optional[int] = ..., total_subjects: _Optional[int] = ..., iterations: _Optional[int] = ..., idle_hours: _Optional[int] = ..., idle_hours_before: _Optional[int] = ..., improvements: _Optional[int] = ..., elapsed_seconds: _Optional[float] = ..., total_blocks: _Optional[int] = ...) -> None: ...

class ListScheduleRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ScheduleEntry(_message.Message):
    __slots__ = ("id", "subject_id", "classroom_id", "weekday", "start_hour", "end_hour")
    ID_FIELD_NUMBER: _ClassVar[int]
    SUBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    CLASSROOM_ID_FIELD_NUMBER: _ClassVar[int]
    WEEKDAY_FIELD_NUMBER: _ClassVar[int]
    START_HOUR_FIELD_NUMBER: _ClassVar[int]
    END_HOUR_FIELD_NUMBER: _ClassVar[int]
    id: int
    subject_id: int
    classroom_id: int
    weekday: Weekday
    start_hour: int
    end_hour: int
    def __init__(self, id: _Optional[int] = ..., subject_id: _Optional[int] = ..., classroom_id: _Optional[int] = ..., weekday: _Optional[_Union[Weekday, str]] = ..., start_hour: _Optional[int] = ..., end_hour: _Optional[int] = ...) -> None: ...

class ListScheduleResponse(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[ScheduleEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[ScheduleEntry, _Mapping]]] = ...) -> None: ...
