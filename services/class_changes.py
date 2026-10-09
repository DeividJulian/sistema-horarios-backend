"""Changes a teacher can make to their own classes, and the notices the students of the group receive."""
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Cancellation, Classroom, Notification, ScheduleEntry, Subject, User
from services.csp import classroom_fits
from time_format import format_date, format_hour

WEEKDAY_INDEX = {"Lunes": 0, "Martes": 1, "Miércoles": 2, "Jueves": 3, "Viernes": 4}

# Colombia has no daylight saving time; the server (Render) runs in UTC, which is already "tomorrow" at 7 p. m.
COLOMBIA = timezone(timedelta(hours=-5))


def today() -> date:
    return datetime.now(COLOMBIA).date()


def get_entry_for_change(db: Session, entry_id: int, user: User) -> ScheduleEntry:
    """The block, if the user may change it: its teacher or an administrator."""
    entry = db.get(ScheduleEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    is_owner = user.rol == "profesor" and user.profesor_id == entry.subject.profesor_id
    if user.rol != "admin" and not is_owner:
        raise HTTPException(status_code=403, detail="Solo el profesor de esta clase o un administrador puede cambiarla.")
    return entry


def notify_group(db: Session, entry: ScheduleEntry, kind: str, title: str, message: str) -> None:
    db.add(
        Notification(
            grupo_id=entry.subject.grupo_id,
            materia_id=entry.materia_id,
            horario_id=entry.id,
            tipo=kind,
            titulo=title,
            mensaje=message,
        )
    )


def describe(entry: ScheduleEntry) -> str:
    """"Bases de Datos (lunes, 6:00 p. m.)"."""
    return f"{entry.subject.nombre} ({entry.dia_semana.lower()}, {format_hour(entry.hora_inicio.hour)})"


def cancel_class(db: Session, entry: ScheduleEntry, day: date, reason: str, user: User) -> Cancellation:
    if day.weekday() != WEEKDAY_INDEX[entry.dia_semana]:
        raise HTTPException(status_code=422, detail=f"Esa fecha no es {entry.dia_semana.lower()}, el día de esta clase.")
    if day < today():
        raise HTTPException(status_code=422, detail="No se puede cancelar una clase que ya pasó.")
    already = db.query(Cancellation).filter(Cancellation.horario_id == entry.id, Cancellation.fecha == day).first()
    if already:
        raise HTTPException(status_code=409, detail="Esa clase ya está cancelada para esa fecha.")

    cancellation = Cancellation(horario_id=entry.id, fecha=day, motivo=reason, usuario_id=user.id)
    db.add(cancellation)
    notify_group(
        db,
        entry,
        "cancelacion",
        f"Clase cancelada: {entry.subject.nombre}",
        f"La clase de {entry.subject.nombre} del {format_date(day)} a las {format_hour(entry.hora_inicio.hour)} "
        f"en {entry.classroom.nombre} no se dictará. Motivo: {reason}",
    )
    db.commit()
    db.refresh(cancellation)
    return cancellation


def restore_class(db: Session, cancellation: Cancellation) -> None:
    entry = cancellation.entry
    notify_group(
        db,
        entry,
        "restablecida",
        f"Clase restablecida: {entry.subject.nombre}",
        f"La clase de {entry.subject.nombre} del {format_date(cancellation.fecha)} a las "
        f"{format_hour(entry.hora_inicio.hour)} sí se dictará, en {entry.classroom.nombre}.",
    )
    db.delete(cancellation)
    db.commit()


def change_classroom(db: Session, entry: ScheduleEntry, classroom_id: int) -> ScheduleEntry:
    classroom = db.get(Classroom, classroom_id)
    if classroom is None:
        raise HTTPException(status_code=404, detail="Aula no encontrada")
    if classroom.id == entry.aula_id:
        raise HTTPException(status_code=409, detail="La clase ya está en esa aula.")
    subject: Subject = entry.subject
    if not classroom_fits(classroom, subject, subject.group.num_estudiantes):
        raise HTTPException(
            status_code=409,
            detail=f"{classroom.nombre} no sirve para {subject.nombre}: no tiene el aforo o el tipo de aula necesarios.",
        )
    taken = (
        db.query(ScheduleEntry)
        .filter(
            ScheduleEntry.id != entry.id,
            ScheduleEntry.aula_id == classroom.id,
            ScheduleEntry.dia_semana == entry.dia_semana,
            ScheduleEntry.hora_inicio == entry.hora_inicio,
        )
        .first()
    )
    if taken:
        raise HTTPException(status_code=409, detail=f"{classroom.nombre} ya está ocupada a esa hora.")

    previous = entry.classroom.nombre
    entry.aula_id = classroom.id
    notify_group(
        db,
        entry,
        "cambio_aula",
        f"Cambio de aula: {subject.nombre}",
        f"Desde ahora la clase de {describe(entry)} es en {classroom.nombre} (antes en {previous}).",
    )
    db.commit()
    db.refresh(entry)
    return entry


def delete_cancellations(db: Session, entry_ids: list[int] | None = None) -> None:
    """Removes the cancellations of the given blocks (all of them with None) before deleting the blocks."""
    query = db.query(Cancellation)
    if entry_ids is not None:
        if not entry_ids:
            return
        query = query.filter(Cancellation.horario_id.in_(entry_ids))
    query.delete(synchronize_session=False)
