from datetime import time

from pydantic import BaseModel


class ProfesorCreate(BaseModel):
    nombre: str
    email: str


class ProfesorOut(ProfesorCreate):
    id: int

    class Config:
        from_attributes = True


class DisponibilidadCreate(BaseModel):
    profesor_id: int
    dia_semana: str
    hora_inicio: time
    hora_fin: time


class DisponibilidadOut(DisponibilidadCreate):
    id: int

    class Config:
        from_attributes = True


class AulaCreate(BaseModel):
    nombre: str
    aforo: int


class AulaOut(AulaCreate):
    id: int

    class Config:
        from_attributes = True


class GrupoCreate(BaseModel):
    nombre: str
    num_estudiantes: int


class GrupoOut(GrupoCreate):
    id: int

    class Config:
        from_attributes = True


class MateriaCreate(BaseModel):
    nombre: str
    intensidad_horaria: int
    grupo_id: int
    profesor_id: int


class MateriaOut(MateriaCreate):
    id: int

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
