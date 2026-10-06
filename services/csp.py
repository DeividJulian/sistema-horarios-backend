import time as clock
from collections import defaultdict
from datetime import time

from sqlalchemy.orm import Session

from models import Classroom, TeacherAvailability, StudentGroup, Subject

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# A group cannot have more than this number of class hours on the same day
MAX_GROUP_HOURS_PER_DAY = 4

# A subject can be taught in consecutive blocks of up to this many hours on the same day
MAX_CONSECUTIVE_SUBJECT_HOURS = 4

# Maximum time (seconds) the algorithm may search before giving up
TIME_LIMIT_SECONDS = 10


class TimeLimitExceeded(Exception):
    pass


# Range of possible start hours (matches the validation in schemas.py)
MIN_HOUR = 6
MAX_HOUR = 22

# Shift of each group: (hour the first class may start, hour the last class must end)
SHIFTS = {
    "todo": (6, 22),  # no restriction: default for every group
    "manana": (7, 13),
    "tarde": (13, 18),
    "noche": (18, 22),
}
# How the user reads each shift in messages
SHIFT_LABELS = {"todo": "cualquier hora", "manana": "la mañana", "tarde": "la tarde", "noche": "la noche"}


def shift_range(shift: str) -> tuple[int, int]:
    return SHIFTS.get(shift, SHIFTS["todo"])


# How the user reads the room type a subject needs
ROOM_TYPE_LABELS = {"cualquiera": "un aula", "informatica": "una sala de informática", "laboratorio": "un laboratorio"}


def classroom_fits(classroom, subject, students: int) -> bool:
    """A classroom fits a subject when it is big enough and of the required type (if any)."""
    required = subject.tipo_aula or "cualquiera"
    return classroom.aforo >= students and (required == "cualquiera" or classroom.tipo == required)


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


def _availability_shortage(subjects, usable_slots, classrooms):
    """
    Cheap checks before searching, so the user learns exactly what is missing. Returns a message or None.
    1. Each subject needs at least one classroom of the right type and size.
    2. Each subject needs enough of its teacher's availability inside its group's shift.
    3. Each teacher needs enough hours for ALL their subjects together.
    """
    for s in subjects:
        students = s.group.num_estudiantes
        if not any(classroom_fits(c, s, students) for c in classrooms):
            needs = ROOM_TYPE_LABELS.get(s.tipo_aula, s.tipo_aula)
            return (
                f"Ninguna aula sirve para '{s.nombre}' ({s.group.nombre}): necesita {needs} con aforo para {students} "
                "estudiantes. Agrega un aula así o cambia el tipo de aula de la materia."
            )

    for s in subjects:
        available = len(usable_slots(s))
        if available < s.intensidad_horaria:
            shift = s.group.jornada
            in_shift = "" if shift == "todo" else f" en {SHIFT_LABELS.get(shift, shift)}"
            return (
                f"{s.teacher.nombre} tiene {available} h disponibles{in_shift} y '{s.nombre}' ({s.group.nombre}) "
                f"necesita {s.intensidad_horaria} h. Agrega disponibilidad al profesor"
                f"{' en la jornada del grupo' if in_shift else ''}."
            )

    by_teacher = defaultdict(list)
    for s in subjects:
        by_teacher[s.profesor_id].append(s)
    for teacher_subjects in by_teacher.values():
        available = len(set().union(*(usable_slots(s) for s in teacher_subjects)))
        needed = sum(s.intensidad_horaria for s in teacher_subjects)
        if available < needed:
            names = ", ".join(f"'{s.nombre}'" for s in teacher_subjects)
            return (
                f"{teacher_subjects[0].teacher.nombre} tiene {available} h disponibles y sus materias ({names}) "
                f"necesitan {needed} h. Agrega más franjas de disponibilidad al profesor."
            )
    return None


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

    def usable_slots(subject):
        """Slots where a subject can be taught: its teacher's availability inside its group's shift."""
        group = groups.get(subject.grupo_id)
        start, end = shift_range(group.jornada if group else "todo")
        return {(d, h) for (d, h) in availability_by_teacher.get(subject.profesor_id, set()) if start <= h.hour < end}

    shortage = _availability_shortage(subjects, usable_slots, classrooms)
    if shortage:
        return False, [], shortage

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
            len(usable_slots(s)) / s.intensidad_horaria,
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

        teacher_slots = usable_slots(subject)
        valid_classrooms = sorted(
            (c for c in classrooms if classroom_fits(c, subject, group.num_estudiantes)), key=lambda c: (c.aforo, c.id)
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

        def sort_key(day, hour):
            penalty = slot_cost(subject.profesor_id, busy_teacher, day, hour) + slot_cost(
                subject.grupo_id, busy_group, day, hour
            )
            return (penalty, _weekday_order(day), hour)

        # A candidate is a block of 1 to N consecutive hours on one day and in one classroom.
        # Short blocks are tried first (spreading the subject over several days), so the hours are
        # only grouped on the same day when the teacher's availability requires it.
        max_length = min(subject.intensidad_horaria, MAX_CONSECUTIVE_SUBJECT_HOURS, MAX_GROUP_HOURS_PER_DAY)
        candidates = []
        for day, hour in teacher_slots:
            for length in range(1, max_length + 1):
                if all((day, time(hour=hour.hour + k)) in teacher_slots for k in range(length)):
                    for classroom in valid_classrooms:
                        candidates.append((day, hour, length, classroom))
        candidates.sort(key=lambda c: (c[2], *sort_key(c[0], c[1]), c[3].aforo, c[3].id))

        def assign_blocks(remaining, used_days, start_at):
            if remaining == 0:
                # Subject complete: move on to the next one. If that fails, other
                # combinations of THIS subject are tried (real backtracking).
                return assign_subject(index + 1)

            for i in range(start_at, len(candidates)):
                if clock.monotonic() > deadline:
                    raise TimeLimitExceeded()
                day, hour, length, classroom = candidates[i]
                if length > remaining or day in used_days:
                    continue
                if group_hours_per_day.get((subject.grupo_id, day), 0) + length > MAX_GROUP_HOURS_PER_DAY:
                    continue
                hours = [time(hour=hour.hour + k) for k in range(length)]
                teacher_keys = [(subject.profesor_id, day, h) for h in hours]
                classroom_keys = [(classroom.id, day, h) for h in hours]
                group_keys = [(subject.grupo_id, day, h) for h in hours]
                if (
                    any(k in busy_teacher for k in teacher_keys)
                    or any(k in busy_classroom for k in classroom_keys)
                    or any(k in busy_group for k in group_keys)
                ):
                    continue

                busy_teacher.update(teacher_keys)
                busy_classroom.update(classroom_keys)
                busy_group.update(group_keys)
                group_hours_per_day[(subject.grupo_id, day)] = group_hours_per_day.get((subject.grupo_id, day), 0) + length
                result.extend((subject, classroom, day, h) for h in hours)
                used_days.add(day)

                if assign_blocks(remaining - length, used_days, i + 1):
                    return True

                busy_teacher.difference_update(teacher_keys)
                busy_classroom.difference_update(classroom_keys)
                busy_group.difference_update(group_keys)
                group_hours_per_day[(subject.grupo_id, day)] -= length
                del result[-length:]
                used_days.discard(day)
            return False

        return assign_blocks(subject.intensidad_horaria, set(), 0)

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
