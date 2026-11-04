"""Generating and saving the schedule: the same logic for the REST endpoint and the RPC stream."""
import logging
import time as clock
from datetime import time

from sqlalchemy.orm import Session

from models import ScheduleEntry, Subject, User
from services.class_changes import delete_cancellations
from services.csp import compute_assignments

logger = logging.getLogger("schedule.generation")


class GenerationFailed(Exception):
    """No valid schedule with the current data. The message is for the user (Spanish)."""


def generate_and_save(db: Session, progress=None) -> tuple[int, dict]:
    """Runs the CSP + simulated annealing and replaces the schedule. Returns (blocks saved, optimization figures).

    `progress(phase, **figures)` reports each phase as it runs (see compute_assignments), plus "saving".
    """
    started = clock.perf_counter()
    optimization: dict = {}
    success, assignments, message = compute_assignments(db, stats=optimization, progress=progress)
    elapsed = clock.perf_counter() - started
    if not success:
        logger.warning("Generation failed after %.2f s: %s", elapsed, message)
        raise GenerationFailed(message)

    if progress:
        progress("saving", blocks=len(assignments))
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
    return len(assignments), optimization


def schedule_for(db: Session, user: User) -> list[ScheduleEntry]:
    """The weekly schedule a user may see: a student only gets the schedule of the group they study in."""
    query = db.query(ScheduleEntry)
    if user.rol == "estudiante":
        query = query.join(Subject, ScheduleEntry.materia_id == Subject.id).filter(Subject.grupo_id == user.grupo_id)
    return query.all()
