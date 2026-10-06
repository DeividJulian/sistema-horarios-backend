from collections import defaultdict

from sqlalchemy.orm import Session

from models import TeacherAvailability, ScheduleEntry, Subject
from services.csp import ROOM_TYPE_LABELS, SHIFT_LABELS, shift_range
from time_format import format_hour, format_range


def _available_slots(db: Session, teacher_id: int) -> set:
    slots = set()
    for a in db.query(TeacherAvailability).filter(TeacherAvailability.profesor_id == teacher_id):
        for h in range(a.hora_inicio.hour, a.hora_fin.hour):
            slots.add((a.dia_semana, h))
    return slots


def _group_clashes(entries, key, kind, label):
    buckets = defaultdict(list)
    for e in entries:
        buckets[key(e)].append(e)
    conflicts = []
    for (entity, day, hour), blocks in buckets.items():
        if len(blocks) > 1:
            conflicts.append(
                {
                    "tipo": kind,
                    "descripcion": f"{label} {entity} tiene {len(blocks)} clases el {day} a las {format_hour(hour)}",
                    "horario_ids": sorted(b.id for b in blocks),
                }
            )
    return conflicts


def detect_conflicts(db: Session) -> list:
    entries = db.query(ScheduleEntry).all()
    conflicts = []

    conflicts += _group_clashes(
        entries,
        lambda e: (e.subject.teacher.nombre, e.dia_semana, e.hora_inicio.hour),
        "cruce_profesor",
        "El profesor",
    )
    conflicts += _group_clashes(
        entries,
        lambda e: (e.classroom.nombre, e.dia_semana, e.hora_inicio.hour),
        "cruce_aula",
        "El aula",
    )
    conflicts += _group_clashes(
        entries,
        lambda e: (e.subject.group.nombre, e.dia_semana, e.hora_inicio.hour),
        "cruce_grupo",
        "El grupo",
    )

    availability_cache = {}
    for e in entries:
        if e.subject.group.num_estudiantes > e.classroom.aforo:
            conflicts.append(
                {
                    "tipo": "sobrecupo",
                    "descripcion": (
                        f"{e.subject.nombre}: el grupo {e.subject.group.nombre} "
                        f"({e.subject.group.num_estudiantes}) no cabe en {e.classroom.nombre} (aforo {e.classroom.aforo})"
                    ),
                    "horario_ids": [e.id],
                }
            )

        tid = e.subject.profesor_id
        if tid not in availability_cache:
            availability_cache[tid] = _available_slots(db, tid)
        if (e.dia_semana, e.hora_inicio.hour) not in availability_cache[tid]:
            conflicts.append(
                {
                    "tipo": "fuera_de_disponibilidad",
                    "descripcion": (
                        f"{e.subject.teacher.nombre} no está disponible el {e.dia_semana} "
                        f"a las {format_hour(e.hora_inicio.hour)} ({e.subject.nombre})"
                    ),
                    "horario_ids": [e.id],
                }
            )

    for e in entries:
        required = e.subject.tipo_aula or "cualquiera"
        if required != "cualquiera" and e.classroom.tipo != required:
            conflicts.append(
                {
                    "tipo": "tipo_de_aula",
                    "descripcion": (
                        f"{e.subject.nombre} necesita {ROOM_TYPE_LABELS.get(required, required)} y está en "
                        f"{e.classroom.nombre} el {e.dia_semana} a las {format_hour(e.hora_inicio.hour)}"
                    ),
                    "horario_ids": [e.id],
                }
            )

    for e in entries:
        group = e.subject.group
        start, end = shift_range(group.jornada)
        if not start <= e.hora_inicio.hour < end:
            conflicts.append(
                {
                    "tipo": "fuera_de_jornada",
                    "descripcion": (
                        f"{e.subject.nombre}: el grupo {group.nombre} estudia en {SHIFT_LABELS.get(group.jornada, group.jornada)} "
                        f"({format_range(start, end)}) y tiene clase el {e.dia_semana} a las {format_hour(e.hora_inicio.hour)}"
                    ),
                    "horario_ids": [e.id],
                }
            )

    # Weekly hours: scheduled blocks vs. required per subject
    scheduled = defaultdict(list)
    for e in entries:
        scheduled[e.materia_id].append(e.id)
    for s in db.query(Subject).all():
        ids = scheduled.get(s.id, [])
        if len(ids) != s.intensidad_horaria:
            conflicts.append(
                {
                    "tipo": "intensidad_incorrecta",
                    "descripcion": (
                        f"{s.nombre} ({s.group.nombre}) requiere {s.intensidad_horaria} h "
                        f"y tiene {len(ids)} programadas"
                    ),
                    "horario_ids": sorted(ids),
                }
            )

    return conflicts
