"""What the AI does in this project. It only advises: it never changes data by itself.

- Conflict: the system computes the slots and classrooms where a conflicting class fits without breaking any
  rule; the model picks the best one and explains why. The administrator decides whether to move it.
- Notice: from a short reason, the model writes the notice the students of the group receive when a class is
  cancelled or changes classroom. The teacher reviews and edits it before sending.

People's names, emails and phones are never sent to the model (see services/privacy.py).
"""
import json
from collections import defaultdict
from datetime import date

from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import Classroom, ScheduleEntry, Teacher, TeacherAvailability
from services import llm
from services.annealing import _idle_hours
from services.conflicts import detect_conflicts
from services.csp import MAX_GROUP_HOURS_PER_DAY, MAX_HOUR, MIN_HOUR, WEEKDAYS, classroom_fits, shift_range
from services.privacy import Aliases
from time_format import format_date, format_hour

MAX_OPTIONS = 6
NOTICE_MAX_CHARS = 600


class ConflictAdvice(BaseModel):
    recomendada: int
    explicacion: str
    motivos: list[str]


class NoticeDraft(BaseModel):
    titulo: str
    mensaje: str


CONFLICT_SYSTEM = """Eres el asistente de programación académica de una universidad colombiana.
Recibes una clase que tiene conflictos en el horario y una lista de opciones calculadas por el sistema.
Todas las opciones ya cumplen las reglas: disponibilidad del docente, sin cruces de docente, grupo ni aula,
aforo, tipo de aula y jornada del grupo.
Elige la mejor opción para el administrador. Prefiere, en este orden:
- menos horas muertas para el grupo y el docente;
- el mismo día;
- la misma aula.
En "recomendada" va el índice de la opción elegida.
En "explicacion", en español sencillo y en 2 a 4 frases, di cuál es el conflicto y por qué esa opción lo resuelve.
En "motivos" pon de 2 a 4 razones cortas.
Si no hay opciones, pon recomendada = -1 y explica qué debería cambiar el administrador y en qué sección
(Gestión → Profesores para la disponibilidad, Gestión → Aulas para crear un aula).
No inventes opciones, horas ni aulas. Nombra a los docentes solo por su alias (Docente A, Docente B…)."""

NOTICE_SYSTEM = """Redactas avisos para los estudiantes de un grupo universitario en Colombia.
El tono es amable, claro y respetuoso, en español.
El "titulo" tiene como máximo 70 caracteres.
El "mensaje" tiene de 2 a 4 frases y como máximo 500 caracteres, e incluye la materia, la fecha o el día, la hora y el aula.
Si hay un motivo, inclúyelo resumido.
No inventes datos que no estén en la información recibida.
No escribas nombres de personas, correos ni teléfonos. No uses emojis."""


def _teacher_slots(db: Session, teacher_id: int) -> set[tuple[str, int]]:
    slots = set()
    for a in db.query(TeacherAvailability).filter(TeacherAvailability.profesor_id == teacher_id):
        for h in range(a.hora_inicio.hour, a.hora_fin.hour):
            slots.add((a.dia_semana, h))
    return slots


def alternatives(db: Session, entry: ScheduleEntry) -> list[dict]:
    """Slots and classrooms where this one-hour class fits without breaking any hard rule, best first."""
    subject = entry.subject
    group = subject.group
    others = [e for e in db.query(ScheduleEntry).all() if e.id != entry.id]
    teacher_busy, group_busy, room_busy = set(), set(), set()
    group_hours, teacher_hours = defaultdict(list), defaultdict(list)
    subject_days = defaultdict(list)
    for e in others:
        h = e.hora_inicio.hour
        teacher_busy.add((e.subject.profesor_id, e.dia_semana, h))
        group_busy.add((e.subject.grupo_id, e.dia_semana, h))
        room_busy.add((e.aula_id, e.dia_semana, h))
        if e.subject.grupo_id == group.id:
            group_hours[e.dia_semana].append(h)
        if e.subject.profesor_id == subject.profesor_id:
            teacher_hours[e.dia_semana].append(h)
        if e.materia_id == subject.id:
            subject_days[e.dia_semana].append(h)

    rooms = sorted(
        (c for c in db.query(Classroom).all() if classroom_fits(c, subject, group.num_estudiantes)),
        key=lambda c: (c.id != entry.aula_id, c.aforo),  # the current classroom first, then the smallest that fits
    )
    slots = _teacher_slots(db, subject.profesor_id)
    start, end = shift_range(group.jornada)
    options = []
    for day in WEEKDAYS:
        if len(group_hours[day]) >= MAX_GROUP_HOURS_PER_DAY:
            continue
        for h in range(max(start, MIN_HOUR), min(end, MAX_HOUR)):
            if (day, h) not in slots or (subject.profesor_id, day, h) in teacher_busy or (group.id, day, h) in group_busy:
                continue
            # Blocks of a subject go on different days, unless they are consecutive hours
            if subject_days[day] and all(abs(h - other) != 1 for other in subject_days[day]):
                continue
            room = next((c for c in rooms if (c.id, day, h) not in room_busy), None)
            if room is None or (day == entry.dia_semana and h == entry.hora_inicio.hour and room.id == entry.aula_id):
                continue
            options.append(
                {
                    "dia_semana": day,
                    "hora": h,
                    "aula_id": room.id,
                    "aula": room.nombre,
                    "aforo": room.aforo,
                    "horas_muertas_grupo": _idle_hours(sorted(group_hours[day] + [h])),
                    "horas_muertas_profesor": _idle_hours(sorted(teacher_hours[day] + [h])),
                    "mismo_dia": day == entry.dia_semana,
                    "misma_aula": room.id == entry.aula_id,
                }
            )
    options.sort(
        key=lambda o: (
            o["horas_muertas_grupo"] + o["horas_muertas_profesor"],
            not o["mismo_dia"],
            not o["misma_aula"],
            WEEKDAYS.index(o["dia_semana"]),
            o["hora"],
        )
    )
    return [{"indice": i, **o} for i, o in enumerate(options[:MAX_OPTIONS])]


def suggest_for_conflict(db: Session, entry: ScheduleEntry) -> dict:
    subject = entry.subject
    aliases = Aliases()
    for teacher in db.query(Teacher).all():
        aliases.alias(teacher.nombre)
    conflicts = [c["descripcion"] for c in detect_conflicts(db) if entry.id in c["horario_ids"]]
    options = alternatives(db, entry)
    context = {
        "clase": {
            "materia": subject.nombre,
            "grupo": subject.group.nombre,
            "estudiantes": subject.group.num_estudiantes,
            "tipo_aula": subject.tipo_aula,
            "docente": aliases.alias(subject.teacher.nombre),
            "actual": {"dia": entry.dia_semana, "hora": format_hour(entry.hora_inicio.hour), "aula": entry.classroom.nombre},
        },
        "conflictos": [aliases.redact(c) for c in conflicts] or ["No se detectan conflictos en esta clase."],
        "opciones": [
            {k: (format_hour(v) if k == "hora" else v) for k, v in o.items() if k != "aula_id"} for o in options
        ],
    }
    advice = llm.generate(CONFLICT_SYSTEM, json.dumps(context, ensure_ascii=False), ConflictAdvice)
    recommended = advice.recomendada if 0 <= advice.recomendada < len(options) else None
    config = llm.current_config()
    return {
        "horario_id": entry.id,
        "conflictos": conflicts,
        "opciones": [
            {**{k: v for k, v in o.items() if k != "hora"}, "hora_inicio": f"{o['hora']:02d}:00:00"} for o in options
        ],
        "recomendada": recommended,
        "explicacion": aliases.restore(advice.explicacion),
        "motivos": [aliases.restore(m) for m in advice.motivos][:4],
        "proveedor": config.label,
        "modelo": config.model,
    }


def draft_notice(db: Session, entry: ScheduleEntry, kind: str, day: date | None, classroom: Classroom | None,
                 reason: str | None) -> dict:
    subject = entry.subject
    aliases = Aliases()
    for teacher in db.query(Teacher).all():
        aliases.alias(teacher.nombre)
    facts = {
        "tipo": "Clase cancelada" if kind == "cancelacion" else "Cambio de aula",
        "materia": subject.nombre,
        "grupo": subject.group.nombre,
        "dia": entry.dia_semana,
        "fecha": format_date(day) if day else None,
        "hora": format_hour(entry.hora_inicio.hour),
        "aula_actual": entry.classroom.nombre,
        "aula_nueva": classroom.nombre if classroom else None,
        "motivo": aliases.redact(reason) if reason else None,
    }
    draft = llm.generate(NOTICE_SYSTEM, json.dumps(facts, ensure_ascii=False), NoticeDraft)
    config = llm.current_config()
    return {
        "titulo": aliases.restore(draft.titulo)[:120],
        "mensaje": aliases.restore(draft.mensaje)[:NOTICE_MAX_CHARS],
        "proveedor": config.label,
        "modelo": config.model,
    }
