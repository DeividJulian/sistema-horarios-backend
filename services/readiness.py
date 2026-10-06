"""
Readiness check: everything that would stop the generator, explained in plain Spanish and with the
section of the app where it is fixed. Unlike the generator (which stops at the first problem), this
lists all of them so the user can fix everything in one pass.
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from models import Classroom, StudentGroup, Subject, Teacher, TeacherAvailability
from services.csp import (
    MAX_GROUP_HOURS_PER_DAY,
    ROOM_TYPE_LABELS,
    SHIFT_LABELS,
    WEEKDAYS,
    classroom_fits,
    shift_range,
    split_into_hour_blocks,
)
from time_format import format_range


def _problem(kind: str, message: str, section: str, teacher_id: int | None = None) -> dict:
    # Keys are part of the API contract (Spanish)
    return {"tipo": kind, "mensaje": message, "seccion": section, "profesor_id": teacher_id}


def check_readiness(db: Session) -> dict:
    classrooms = db.query(Classroom).all()
    groups = db.query(StudentGroup).all()
    teachers = db.query(Teacher).all()
    subjects = db.query(Subject).all()
    problems = []

    if not classrooms:
        problems.append(_problem("sin_aulas", "Todavía no hay aulas. Agrega al menos una.", "aulas"))
    if not groups:
        problems.append(_problem("sin_grupos", "Todavía no hay grupos. Agrega al menos uno.", "grupos"))
    if not teachers:
        problems.append(_problem("sin_profesores", "Todavía no hay profesores. Agrega al menos uno.", "profesores"))
    if not subjects:
        problems.append(_problem("sin_materias", "Todavía no hay materias. Crea las materias de cada grupo.", "materias"))

    slots_by_teacher = defaultdict(set)
    for a in db.query(TeacherAvailability).all():
        for h in split_into_hour_blocks(a.hora_inicio, a.hora_fin):
            slots_by_teacher[a.profesor_id].add((a.dia_semana, h.hour))

    def usable(subject) -> set:
        start, end = shift_range(subject.group.jornada)
        return {(d, h) for (d, h) in slots_by_teacher[subject.profesor_id] if start <= h < end}

    subjects_by_teacher = defaultdict(list)
    for s in subjects:
        subjects_by_teacher[s.profesor_id].append(s)

    for teacher_id, teacher_subjects in subjects_by_teacher.items():
        name = teacher_subjects[0].teacher.nombre
        if not slots_by_teacher[teacher_id]:
            problems.append(_problem(
                "sin_disponibilidad",
                f"{name} no tiene disponibilidad. Marca las horas en que puede dar clase.",
                "profesores", teacher_id,
            ))
            continue
        for s in teacher_subjects:
            available = len(usable(s))
            if available < s.intensidad_horaria:
                shift = s.group.jornada
                if shift == "todo":
                    where = ""
                else:
                    start, end = shift_range(shift)
                    where = f" en {SHIFT_LABELS[shift]} ({format_range(start, end)}), que es la jornada de {s.group.nombre}"
                problems.append(_problem(
                    "poca_disponibilidad",
                    f"{name} tiene {available} h disponibles{where} y '{s.nombre}' necesita {s.intensidad_horaria} h.",
                    "profesores", teacher_id,
                ))
        total_available = len(set().union(*(usable(s) for s in teacher_subjects)))
        total_needed = sum(s.intensidad_horaria for s in teacher_subjects)
        if total_available < total_needed and not any(p["profesor_id"] == teacher_id for p in problems):
            problems.append(_problem(
                "poca_disponibilidad",
                f"{name} dicta {total_needed} h por semana pero solo tiene {total_available} h disponibles en las jornadas de sus grupos.",
                "profesores", teacher_id,
            ))

    for s in subjects:
        if classrooms and not any(classroom_fits(c, s, s.group.num_estudiantes) for c in classrooms):
            needs = ROOM_TYPE_LABELS.get(s.tipo_aula, s.tipo_aula)
            problems.append(_problem(
                "sin_aula_adecuada",
                f"Ninguna aula sirve para '{s.nombre}': necesita {needs} con espacio para {s.group.num_estudiantes} estudiantes.",
                "aulas",
            ))

    hours_by_group = defaultdict(int)
    for s in subjects:
        hours_by_group[s.grupo_id] += s.intensidad_horaria
    for g in groups:
        start, end = shift_range(g.jornada)
        capacity = len(WEEKDAYS) * min(end - start, MAX_GROUP_HOURS_PER_DAY)
        if hours_by_group[g.id] > capacity:
            problems.append(_problem(
                "grupo_sin_espacio",
                f"{g.nombre} tiene {hours_by_group[g.id]} h de clase por semana, pero en su jornada caben máximo {capacity} h "
                f"({MAX_GROUP_HOURS_PER_DAY} h por día). Quita horas o cambia la jornada del grupo.",
                "grupos",
            ))

    return {"listo": not problems, "problemas": problems}
