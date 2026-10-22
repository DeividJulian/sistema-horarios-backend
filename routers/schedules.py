import logging
import time as clock
from datetime import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Classroom, ScheduleEntry, Subject, Teacher, User
from schemas import ScheduleEntryMove, ScheduleEntryOut
from security import get_current_user
from services.class_changes import delete_cancellations, describe, notify_group
from services.csp import SHIFT_LABELS, classroom_fits, compute_assignments, shift_range
from time_format import format_range

logger = logging.getLogger("schedule.generation")

router = APIRouter(tags=["Horarios"])


@router.post("/schedules/generate")
def generate_schedule(db: Session = Depends(get_db)):
    started = clock.perf_counter()
    optimization = {}
    success, assignments, message = compute_assignments(db, stats=optimization)
    elapsed = clock.perf_counter() - started
    if not success:
        logger.warning("Generation failed after %.2f s: %s", elapsed, message)
        raise HTTPException(status_code=409, detail=message)

    delete_cancellations(db)
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
    logger.info(
        "Schedule generated: %d blocks in %.2f s (idle hours %s -> %s)",
        len(assignments), elapsed, optimization.get("horas_muertas_antes"), optimization.get("horas_muertas_despues"),
    )
    return {"mensaje": "Horario generado exitosamente", "total_bloques": len(assignments), "optimizacion": optimization}


@router.get("/schedules", response_model=List[ScheduleEntryOut])
def list_schedule(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(ScheduleEntry)
    if user.rol == "estudiante":
        # A student only sees the schedule of the group they study in
        query = query.join(Subject, ScheduleEntry.materia_id == Subject.id).filter(Subject.grupo_id == user.grupo_id)
    return query.all()


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

    room_id = entry.aula_id
    if data.aula_id is not None and data.aula_id != entry.aula_id:
        classroom = db.get(Classroom, data.aula_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail="Aula no encontrada")
        if not classroom_fits(classroom, subject, subject.group.num_estudiantes):
            raise HTTPException(
                status_code=409,
                detail=f"{classroom.nombre} no sirve para {subject.nombre}: no tiene el aforo o el tipo de aula necesarios.",
            )
        room_id = classroom.id

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
        if other.aula_id == room_id:
            raise HTTPException(status_code=409, detail="El aula ya está ocupada en esa franja")
        if other.subject.profesor_id == subject.profesor_id:
            raise HTTPException(status_code=409, detail="El profesor ya tiene clase en esa franja")
        if other.subject.grupo_id == subject.grupo_id:
            raise HTTPException(status_code=409, detail="El grupo ya tiene clase en esa franja")

    moved = (entry.dia_semana, entry.hora_inicio) != (data.dia_semana, data.hora_inicio)
    new_room = room_id != entry.aula_id
    before = describe(entry)
    entry.aula_id = room_id
    entry.dia_semana = data.dia_semana
    entry.hora_inicio = data.hora_inicio
    entry.hora_fin = new_end
    if moved:
        # Cancellations were for the old day, so they no longer apply
        delete_cancellations(db, [entry.id])
    if moved or new_room:
        db.flush()
        db.refresh(entry)
        notify_group(
            db, entry, "cambio_horario", f"Cambio de horario: {subject.nombre}",
            f"La clase de {before} pasa a {describe(entry)} en {entry.classroom.nombre}.",
        )
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/schedules/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(ScheduleEntry).filter(ScheduleEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    delete_cancellations(db, [entry.id])
    db.delete(entry)
    db.commit()
    return {"mensaje": "Bloque de horario eliminado"}
