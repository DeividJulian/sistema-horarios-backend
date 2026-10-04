from datetime import time
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]


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
    dia_semana: str
    hora_inicio: time
    hora_fin: time


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
    dia_semana: str
    hora_inicio: time
