import logging
import time as reloj
from datetime import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Classroom, ScheduleEntry, Subject, Teacher
from schemas import ScheduleEntryOut, ScheduleEntryMove
from services.csp import compute_assignments

logger = logging.getLogger("horarios.generacion")

router = APIRouter(tags=["Horarios"])


@router.post("/generar-horario")
def generar_horario(db: Session = Depends(get_db)):
    inicio = reloj.perf_counter()
    exito, asignaciones, mensaje = compute_assignments(db)
    duracion = reloj.perf_counter() - inicio
    if not exito:
        logger.warning("Generación fallida tras %.2f s: %s", duracion, mensaje)
        raise HTTPException(status_code=409, detail=mensaje)

    db.query(ScheduleEntry).delete()
    for subject, classroom, dia, hora in asignaciones:
        db.add(
            ScheduleEntry(
                materia_id=subject.id,
                aula_id=classroom.id,
                dia_semana=dia,
                hora_inicio=hora,
                hora_fin=time(hour=hora.hour + 1),
            )
        )
    db.commit()
    logger.info("Horario generado: %d bloques en %.2f s", len(asignaciones), duracion)
    return {"mensaje": "Horario generado exitosamente", "total_bloques": len(asignaciones)}


@router.get("/horarios", response_model=List[ScheduleEntryOut])
def listar_horarios(db: Session = Depends(get_db)):
    return db.query(ScheduleEntry).all()


@router.get("/horarios/grupo/{grupo_id}", response_model=List[ScheduleEntryOut])
def horarios_por_grupo(grupo_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ScheduleEntry)
        .join(Subject, ScheduleEntry.materia_id == Subject.id)
        .filter(Subject.grupo_id == grupo_id)
        .all()
    )


@router.get("/horarios/profesor/{profesor_id}", response_model=List[ScheduleEntryOut])
def horarios_por_profesor(profesor_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == profesor_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    return (
        db.query(ScheduleEntry)
        .join(Subject, ScheduleEntry.materia_id == Subject.id)
        .filter(Subject.profesor_id == profesor_id)
        .order_by(ScheduleEntry.dia_semana, ScheduleEntry.hora_inicio)
        .all()
    )


@router.get("/horarios/aula/{aula_id}", response_model=List[ScheduleEntryOut])
def horarios_por_aula(aula_id: int, db: Session = Depends(get_db)):
    classroom = db.query(Classroom).filter(Classroom.id == aula_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    return (
        db.query(ScheduleEntry)
        .filter(ScheduleEntry.aula_id == aula_id)
        .order_by(ScheduleEntry.dia_semana, ScheduleEntry.hora_inicio)
        .all()
    )


@router.put("/horarios/{horario_id}", response_model=ScheduleEntryOut)
def mover_horario(horario_id: int, datos: ScheduleEntryMove, db: Session = Depends(get_db)):
    horario = db.query(ScheduleEntry).filter(ScheduleEntry.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    subject = db.query(Subject).filter(Subject.id == horario.materia_id).first()
    nueva_fin = time(hour=datos.hora_inicio.hour + 1)

    # Otros bloques que caen en la misma franja
    mismos = (
        db.query(ScheduleEntry)
        .join(Subject, ScheduleEntry.materia_id == Subject.id)
        .filter(
            ScheduleEntry.id != horario_id,
            ScheduleEntry.dia_semana == datos.dia_semana,
            ScheduleEntry.hora_inicio == datos.hora_inicio,
        )
        .all()
    )
    for otro in mismos:
        if otro.aula_id == horario.aula_id:
            raise HTTPException(status_code=409, detail="El aula ya está ocupada en esa franja")
        if otro.subject.profesor_id == subject.profesor_id:
            raise HTTPException(status_code=409, detail="El profesor ya tiene clase en esa franja")
        if otro.subject.grupo_id == subject.grupo_id:
            raise HTTPException(status_code=409, detail="El grupo ya tiene clase en esa franja")

    horario.dia_semana = datos.dia_semana
    horario.hora_inicio = datos.hora_inicio
    horario.hora_fin = nueva_fin
    db.commit()
    db.refresh(horario)
    return horario


@router.delete("/horarios/{horario_id}")
def eliminar_horario(horario_id: int, db: Session = Depends(get_db)):
    horario = db.query(ScheduleEntry).filter(ScheduleEntry.id == horario_id).first()
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    db.delete(horario)
    db.commit()
    return {"mensaje": "Bloque de horario eliminado"}
