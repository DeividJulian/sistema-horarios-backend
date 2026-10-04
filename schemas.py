from datetime import time
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]

DiaSemana = Literal["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# Rango del calendario: los bloques empiezan entre las 6:00 y las 20:00 y terminan a las 21:00 como maximo
HORA_MIN = 6
HORA_MAX = 21


def exigir_hora_en_punto(valor: time) -> time:
    if valor.minute != 0 or valor.second != 0:
        raise ValueError("Las horas deben ser en punto (por ejemplo 08:00:00)")
    return valor


class ProfesorCreate(BaseModel):
    nombre: Nombre
    email: EmailStr


class ProfesorOut(BaseModel):
    id: int
    nombre: str
    email: str

    class Config:
        from_attributes = True


class DisponibilidadCreate(BaseModel):
    profesor_id: int = Field(gt=0)
    dia_semana: DiaSemana
    hora_inicio: time
    hora_fin: time

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def validar_hora_en_punto(cls, valor: time) -> time:
        return exigir_hora_en_punto(valor)

    @model_validator(mode="after")
    def validar_rango(self):
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser posterior a hora_inicio")
        if self.hora_inicio.hour < HORA_MIN or self.hora_fin.hour > HORA_MAX:
            raise ValueError(
                f"La disponibilidad debe estar entre las {HORA_MIN}:00 y las {HORA_MAX}:00"
            )
        return self


class DisponibilidadOut(BaseModel):
    id: int
    profesor_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time

    class Config:
        from_attributes = True


class AulaCreate(BaseModel):
    nombre: Nombre
    aforo: int = Field(ge=1, le=500)


class AulaOut(BaseModel):
    id: int
    nombre: str
    aforo: int

    class Config:
        from_attributes = True


class GrupoCreate(BaseModel):
    nombre: Nombre
    num_estudiantes: int = Field(ge=1, le=500)


class GrupoOut(BaseModel):
    id: int
    nombre: str
    num_estudiantes: int

    class Config:
        from_attributes = True


class MateriaCreate(BaseModel):
    nombre: Nombre
    intensidad_horaria: int = Field(ge=1, le=5)
    grupo_id: int = Field(gt=0)
    profesor_id: int = Field(gt=0)


class MateriaOut(BaseModel):
    id: int
    nombre: str
    intensidad_horaria: int
    grupo_id: int
    profesor_id: int

    class Config:
        from_attributes = True


class HorarioOut(BaseModel):
    id: int
    materia_id: int
    aula_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time

    class Config:
        from_attributes = True


class HorarioUpdate(BaseModel):
    dia_semana: DiaSemana
    hora_inicio: time

    @field_validator("hora_inicio")
    @classmethod
    def validar_hora_inicio(cls, valor: time) -> time:
        exigir_hora_en_punto(valor)
        if valor.hour < HORA_MIN or valor.hour >= HORA_MAX:
            raise ValueError(
                f"El bloque debe iniciar entre las {HORA_MIN}:00 y las {HORA_MAX - 1}:00"
            )
        return valor
