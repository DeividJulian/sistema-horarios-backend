import time as clock
from datetime import time

from sqlalchemy.orm import Session

from models import Classroom, TeacherAvailability, StudentGroup, Subject

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# A group cannot have more than this number of class hours on the same day
MAX_GROUP_HOURS_PER_DAY = 4

# Maximum time (seconds) the algorithm may search before giving up
TIME_LIMIT_SECONDS = 10


class TimeLimitExceeded(Exception):
    pass


# Range of possible start hours (matches the validation in schemas.py)
MIN_HOUR = 6
MAX_HOUR = 21


def split_into_hour_blocks(start: time, end: time):
    """Turns an availability range into 1-hour blocks."""
    blocks = []
    h = start.hour
    while h < end.hour:
        blocks.append(time(hour=h))
        h += 1
    return blocks


def _weekday_order(day: str) -> int:
    return WEEKDAYS.index(day) if day in WEEKDAYS else len(WEEKDAYS)


def compute_assignments(db: Session):
    subjects = db.query(Subject).all()
    classrooms = db.query(Classroom).all()
    groups = {g.id: g for g in db.query(StudentGroup).all()}

    if not subjects or not classrooms:
        return False, [], "No hay materias o aulas registradas."

    # Each teacher's availability as a set of (day, hour)
    availability_by_teacher = {}
    for subject in subjects:
        tid = subject.profesor_id
        if tid not in availability_by_teacher:
            slots = set()
            availabilities = db.query(TeacherAvailability).filter(
                TeacherAvailability.profesor_id == tid
            ).all()
            for a in availabilities:
                for h in split_into_hour_blocks(a.hora_inicio, a.hora_fin):
                    slots.add((a.dia_semana, h))
            availability_by_teacher[tid] = slots

    # Degree heuristic: how many other subjects share a teacher or group with each one.
    # Subjects with more "neighbours" can cause more clashes, so they are placed first.
    def degree(s):
        return sum(
            1
            for o in subjects
            if o.id != s.id and (o.profesor_id == s.profesor_id or o.grupo_id == s.grupo_id)
        )

    # Order: most constrained first (few slots per hour to place) and, on ties, highest degree
    ordered_subjects = sorted(
        subjects,
        key=lambda s: (
            len(availability_by_teacher.get(s.profesor_id, set())) / s.intensidad_horaria,
            -degree(s),
            s.id,
        ),
    )

    deadline = clock.monotonic() + TIME_LIMIT_SECONDS

    busy_teacher = set()
    busy_classroom = set()
    busy_group = set()
    group_hours_per_day = {}
    result = []

    def assign_subject(index):
        if index == len(ordered_subjects):
            return True

        subject = ordered_subjects[index]
        group = groups.get(subject.grupo_id)
        if group is None:
            return False

        teacher_slots = availability_by_teacher.get(subject.profesor_id, set())
        valid_classrooms = sorted(
            (c for c in classrooms if c.aforo >= group.num_estudiantes), key=lambda c: (c.aforo, c.id)
        )

        def has_class(entity_id, busy, day, h):
            return 0 <= h <= 23 and (entity_id, day, time(hour=h)) in busy

        def slot_cost(entity_id, busy, day, hour):
            """0 if the class sits next to another one, 1 if the day was free, 2 if it opens an idle gap."""
            h = hour.hour
            if has_class(entity_id, busy, day, h - 1) or has_class(entity_id, busy, day, h + 1):
                return 0
            if any(has_class(entity_id, busy, day, x) for x in range(MIN_HOUR, MAX_HOUR)):
                return 2
            return 1

        def sort_key(slot):
            day, hour = slot
            penalty = slot_cost(subject.profesor_id, busy_teacher, day, hour) + slot_cost(
                subject.grupo_id, busy_group, day, hour
            )
            return (penalty, _weekday_order(day), hour)

        # Slots that leave no gaps are tried first; the backtracking is still complete
        candidates = [
            (day, hour, classroom)
            for (day, hour) in sorted(teacher_slots, key=sort_key)
            for classroom in valid_classrooms
        ]

        def assign_blocks(pos, used_days, start_at):
            if pos == subject.intensidad_horaria:
                # Subject complete: move on to the next one. If that fails, other
                # combinations of THIS subject are tried (real backtracking).
                return assign_subject(index + 1)

            for i in range(start_at, len(candidates)):
                if clock.monotonic() > deadline:
                    raise TimeLimitExceeded()
                day, hour, classroom = candidates[i]
                if day in used_days:
                    continue
                if group_hours_per_day.get((subject.grupo_id, day), 0) >= MAX_GROUP_HOURS_PER_DAY:
                    continue
                teacher_key = (subject.profesor_id, day, hour)
                classroom_key = (classroom.id, day, hour)
                group_key = (subject.grupo_id, day, hour)
                if teacher_key in busy_teacher or classroom_key in busy_classroom or group_key in busy_group:
                    continue

                busy_teacher.add(teacher_key)
                busy_classroom.add(classroom_key)
                busy_group.add(group_key)
                group_hours_per_day[(subject.grupo_id, day)] = group_hours_per_day.get((subject.grupo_id, day), 0) + 1
                result.append((subject, classroom, day, hour))
                used_days.add(day)

                if assign_blocks(pos + 1, used_days, i + 1):
                    return True

                busy_teacher.discard(teacher_key)
                busy_classroom.discard(classroom_key)
                busy_group.discard(group_key)
                group_hours_per_day[(subject.grupo_id, day)] -= 1
                result.pop()
                used_days.discard(day)
            return False

        return assign_blocks(0, set(), 0)

    try:
        success = assign_subject(0)
    except TimeLimitExceeded:
        return (
            False,
            [],
            f"El algoritmo superó el límite de {TIME_LIMIT_SECONDS} s sin encontrar solución. "
            "Probablemente no existe un horario válido: revisa disponibilidades, aulas y horas por materia.",
        )

    if not success:
        return False, [], "No fue posible generar un horario sin cruces con los datos actuales. Revisa disponibilidad de profesores o número de aulas disponibles."

    return True, list(result), "OK"
