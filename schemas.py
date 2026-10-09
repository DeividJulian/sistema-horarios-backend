from datetime import time
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from time_format import format_hour

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]

Weekday = Literal["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# Calendar range: blocks start between 6:00 and 21:00 and end at 22:00 at the latest
MIN_HOUR = 6
MAX_HOUR = 22

# Shift of a group (values are part of the API contract, in Spanish)
Shift = Literal["todo", "manana", "tarde", "noche"]

# Room types (API contract, in Spanish)
RoomType = Literal["general", "informatica", "laboratorio"]
RequiredRoomType = Literal["cualquiera", "informatica", "laboratorio"]


def require_on_the_hour(value: time) -> time:
    if value.minute != 0 or value.second != 0:
        raise ValueError("Las horas deben ser en punto, sin minutos (por ejemplo 8:00 a. m.)")
    return value


class TeacherCreate(BaseModel):
    nombre: Name
    email: EmailStr


class TeacherOut(BaseModel):
    id: int
    nombre: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class AvailabilityCreate(BaseModel):
    profesor_id: int = Field(gt=0)
    dia_semana: Weekday
    hora_inicio: time
    hora_fin: time

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def validate_on_the_hour(cls, value: time) -> time:
        return require_on_the_hour(value)

    @model_validator(mode="after")
    def validate_range(self):
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser posterior a hora_inicio")
        if self.hora_inicio.hour < MIN_HOUR or self.hora_fin.hour > MAX_HOUR:
            raise ValueError(
                f"La disponibilidad debe estar entre las {format_hour(MIN_HOUR)} y las {format_hour(MAX_HOUR)}"
            )
        return self


class AvailabilityOut(BaseModel):
    id: int
    profesor_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time

    model_config = ConfigDict(from_attributes=True)


class ClassroomCreate(BaseModel):
    nombre: Name
    aforo: int = Field(ge=1, le=500)
    tipo: RoomType = "general"


class ClassroomOut(BaseModel):
    id: int
    nombre: str
    aforo: int
    tipo: str

    model_config = ConfigDict(from_attributes=True)


class GroupCreate(BaseModel):
    nombre: Name
    num_estudiantes: int = Field(ge=1, le=500)
    jornada: Shift = "todo"


class GroupOut(BaseModel):
    id: int
    nombre: str
    num_estudiantes: int
    jornada: str

    model_config = ConfigDict(from_attributes=True)


class SubjectCreate(BaseModel):
    nombre: Name
    intensidad_horaria: int = Field(ge=1, le=5)
    grupo_id: int = Field(gt=0)
    profesor_id: int = Field(gt=0)
    tipo_aula: RequiredRoomType = "cualquiera"


class SubjectOut(BaseModel):
    id: int
    nombre: str
    intensidad_horaria: int
    grupo_id: int
    profesor_id: int
    tipo_aula: str

    model_config = ConfigDict(from_attributes=True)


class ScheduleEntryOut(BaseModel):
    id: int
    materia_id: int
    aula_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time

    model_config = ConfigDict(from_attributes=True)


class ScheduleEntryMove(BaseModel):
    dia_semana: Weekday
    hora_inicio: time

    @field_validator("hora_inicio")
    @classmethod
    def validate_start_time(cls, value: time) -> time:
        require_on_the_hour(value)
        if value.hour < MIN_HOUR or value.hour >= MAX_HOUR:
            raise ValueError(
                f"El bloque debe iniciar entre las {format_hour(MIN_HOUR)} y las {format_hour(MAX_HOUR - 1)}"
            )
        return value


# ---------- Users and authentication ----------

# Roles (API contract, in Spanish)
Role = Literal["admin", "usuario"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class UserOut(BaseModel):
    id: int
    nombre: str
    email: str
    rol: Role

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    nombre: Name
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]
    rol: Role = "usuario"


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UserOut
