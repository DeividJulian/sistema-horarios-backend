from datetime import time
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Time, ForeignKey, text
from sqlalchemy.orm import relationship, Session
from pydantic import BaseModel
from typing import List

from database import engine, Base, get_db
from models import Profesor, DisponibilidadProfesor, Aula, Grupo, Materia, Horario
from schemas import (
    ProfesorCreate, ProfesorOut,
    DisponibilidadCreate, DisponibilidadOut,
    AulaCreate, AulaOut,
    GrupoCreate, GrupoOut,
    MateriaCreate, MateriaOut,
    HorarioOut, HorarioUpdate,
)
from routers import disponibilidad
from services.csp import calcular_asignaciones
from routers import materias
from routers import grupos
from routers import aulas
from routers import profesores

Base.metadata.create_all(bind=engine)

# ---------- APP ----------

app = FastAPI(title="Sistema de Horarios y Aulas Universitarias")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profesores.router)
app.include_router(aulas.router)
app.include_router(grupos.router)
app.include_router(materias.router)
app.include_router(disponibilidad.router)


@app.get("/")
def root():
    return {"mensaje": "API Sistema de Horarios funcionando"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"estado": "ok", "base_de_datos": "conectada"}


@app.post("/generar-horario", response_model=List[HorarioOut])
def generar_horario(db: Session = Depends(get_db)):
    exito, asignaciones, mensaje = calcular_asignaciones(db)
    if not exito:
        raise HTTPException(status_code=409, detail=mensaje)

    db.query(Horario).delete()
    db.commit()

    for (materia, aula, dia, hora) in asignaciones:
        nueva_hora_fin = time(hour=hora.hour + 1)
        nuevo_horario = Horario(
            materia_id=materia.id,
            aula_id=aula.id,
            dia_semana=dia,
            hora_inicio=hora,
            hora_fin=nueva_hora_fin,
        )
        db.add(nuevo_horario)
    db.commit()

    return db.query(Horario).all()


@app.get("/horarios", response_model=List[HorarioOut])
def listar_horarios(db: Session = Depends(get_db)):
    return db.query(Horario).all()


@app.get("/horarios/grupo/{grupo_id}", response_model=List[HorarioOut])
def listar_horarios_por_grupo(grupo_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Horario)
        .join(Materia, Horario.materia_id == Materia.id)
        .filter(Materia.grupo_id == grupo_id)
        .all()
    )

@app.put("/horarios/{horario_id}", response_model=HorarioOut)
def mover_horario(horario_id: int, cambio: HorarioUpdate, db: Session = Depends(get_db)):
    horario = db.query(Horario).filter(Horario.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    materia = db.query(Materia).filter(Materia.id == horario.materia_id).first()
    nueva_hora_fin = time(hour=cambio.hora_inicio.hour + 1)

    otros_horarios = (
        db.query(Horario)
        .join(Materia, Horario.materia_id == Materia.id)
        .filter(
            Horario.id != horario_id,
            Horario.dia_semana == cambio.dia_semana,
            Horario.hora_inicio == cambio.hora_inicio,
        )
        .all()
    )

    for otro in otros_horarios:
        otra_materia = db.query(Materia).filter(Materia.id == otro.materia_id).first()
        if (
            otro.aula_id == horario.aula_id
            or otra_materia.profesor_id == materia.profesor_id
            or otra_materia.grupo_id == materia.grupo_id
        ):
            raise HTTPException(
                status_code=409,
                detail="Ese horario ya está ocupado (choca con la misma aula, profesor o grupo)."
            )

    horario.dia_semana = cambio.dia_semana
    horario.hora_inicio = cambio.hora_inicio
    horario.hora_fin = nueva_hora_fin
    db.commit()
    db.refresh(horario)
    return horario