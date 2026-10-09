import logging
import time as clock
from datetime import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Classroom, ScheduleEntry, Subject, Teacher
from schemas import ScheduleEntryMove, ScheduleEntryOut
from services.csp import SHIFT_LABELS, compute_assignments, shift_range
from time_format import format_range

logger = logging.getLogger("schedule.generation")

router = APIRouter(tags=["Horarios"])


@router.post("/schedules/generate")
def generate_schedule(db: Session = Depends(get_db)):
    started = clock.perf_counter()
    success, assignments, message = compute_assignments(db)
    elapsed = clock.perf_counter() - started
    if not success:
        logger.warning("Generation failed after %.2f s: %s", elapsed, message)
        raise HTTPException(status_code=409, detail=message)

    db.query(ScheduleEntry).delete()
    for subject, classroom, day, hour in assignments:
        db.add(
            ScheduleEntry(
                materia_id=subject.id,
                aula_id=classroom.id,
                dia_semana=day,
                hora_inicio=hour,
                hora_fin=time(hour=hour.hour + 1),
            )
        )
    db.commit()
    logger.info("Schedule generated: %d blocks in %.2f s", len(assignments), elapsed)
    return {"mensaje": "Horario generado exitosamente", "total_bloques": len(assignments)}


@router.get("/schedules", response_model=List[ScheduleEntryOut])
def list_schedule(db: Session = Depends(get_db)):
    return db.query(ScheduleEntry).all()


@router.get("/schedules/group/{group_id}", response_model=List[ScheduleEntryOut])
def schedule_by_group(group_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ScheduleEntry)
        .join(Subject, ScheduleEntry.materia_id == Subject.id)
        .filter(Subject.grupo_id == group_id)
        .all()
    )


@router.get("/schedules/teacher/{teacher_id}", response_model=List[ScheduleEntryOut])
def schedule_by_teacher(teacher_id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")

    return (
        db.query(ScheduleEntry)
        .join(Subject, ScheduleEntry.materia_id == Subject.id)
        .filter(Subject.profesor_id == teacher_id)
        .order_by(ScheduleEntry.dia_semana, ScheduleEntry.hora_inicio)
        .all()
    )


@router.get("/schedules/classroom/{classroom_id}", response_model=List[ScheduleEntryOut])
def schedule_by_classroom(classroom_id: int, db: Session = Depends(get_db)):
    classroom = db.query(Classroom).filter(Classroom.id == classroom_id).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    return (
        db.query(ScheduleEntry)
        .filter(ScheduleEntry.aula_id == classroom_id)
        .order_by(ScheduleEntry.dia_semana, ScheduleEntry.hora_inicio)
        .all()
    )


@router.put("/schedules/{entry_id}", response_model=ScheduleEntryOut)
def move_entry(entry_id: int, data: ScheduleEntryMove, db: Session = Depends(get_db)):
    entry = db.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    subject = db.query(Subject).filter(Subject.id == entry.materia_id).first()
    new_end = time(hour=data.hora_inicio.hour + 1)

    start, end = shift_range(subject.group.jornada)
    if not start <= data.hora_inicio.hour < end:
        raise HTTPException(
            status_code=409,
            detail=f"El grupo {subject.group.nombre} estudia en {SHIFT_LABELS.get(subject.group.jornada)} ({format_range(start, end)})",
        )

    # Other blocks that fall in the same slot
    same_slot = (
        db.query(ScheduleEntry)
        .join(Subject, ScheduleEntry.materia_id == Subject.id)
        .filter(
            ScheduleEntry.id != entry_id,
            ScheduleEntry.dia_semana == data.dia_semana,
            ScheduleEntry.hora_inicio == data.hora_inicio,
        )
        .all()
    )
    for other in same_slot:
        if other.aula_id == entry.aula_id:
            raise HTTPException(status_code=409, detail="El aula ya está ocupada en esa franja")
        if other.subject.profesor_id == subject.profesor_id:
            raise HTTPException(status_code=409, detail="El profesor ya tiene clase en esa franja")
        if other.subject.grupo_id == subject.grupo_id:
            raise HTTPException(status_code=409, detail="El grupo ya tiene clase en esa franja")

    entry.dia_semana = data.dia_semana
    entry.hora_inicio = data.hora_inicio
    entry.hora_fin = new_end
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/schedules/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    db.delete(entry)
    db.commit()
    return {"mensaje": "Bloque de horario eliminado"}
