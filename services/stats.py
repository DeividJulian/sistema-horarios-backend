from collections import defaultdict

from sqlalchemy.orm import Session

from models import Classroom, StudentGroup, ScheduleEntry, Subject, Teacher

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
# 5 days x 16 possible start hours (6:00 to 21:00)
BLOCKS_PER_WEEK = 5 * 16


def _pct(part: float, total: float) -> float:
    return round(100 * part / total, 1) if total else 0.0


def compute_statistics(db: Session) -> dict:
    entries = db.query(ScheduleEntry).all()
    subjects = db.query(Subject).all()

    required = sum(s.intensidad_horaria for s in subjects)
    scheduled = len(entries)
    fulfillment = _pct(min(scheduled, required), required)

    by_classroom = defaultdict(int)
    by_teacher = defaultdict(list)
    by_day = {d: 0 for d in WEEKDAYS}
    for e in entries:
        by_classroom[e.aula_id] += 1
        by_teacher[e.subject.profesor_id].append((e.dia_semana, e.hora_inicio.hour))
        by_day[e.dia_semana] = by_day.get(e.dia_semana, 0) + 1

    classroom_usage = [
        {
            "aula_id": c.id,
            "aula": c.nombre,
            "aforo": c.aforo,
            "horas_ocupadas": by_classroom.get(c.id, 0),
            "ocupacion_pct": _pct(by_classroom.get(c.id, 0), BLOCKS_PER_WEEK),
        }
        for c in db.query(Classroom).all()
    ]

    teacher_load = []
    for t in db.query(Teacher).all():
        slots = by_teacher.get(t.id, [])
        idle = 0
        for day in WEEKDAYS:
            hours = sorted(h for d, h in slots if d == day)
            if len(hours) > 1:
                idle += (hours[-1] - hours[0] + 1) - len(hours)
        teacher_load.append(
            {
                "profesor_id": t.id,
                "profesor": t.nombre,
                "horas_semanales": len(slots),
                "dias_con_clase": len({d for d, _ in slots}),
                "franjas_muertas": idle,
            }
        )

    return {
        "totales": {
            "profesores": db.query(Teacher).count(),
            "aulas": db.query(Classroom).count(),
            "grupos": db.query(StudentGroup).count(),
            "materias": len(subjects),
            "bloques_programados": scheduled,
        },
        "cumplimiento": {
            "horas_requeridas": required,
            "horas_programadas": scheduled,
            "porcentaje": fulfillment,
        },
        "ocupacion_aulas": classroom_usage,
        "carga_profesores": teacher_load,
        "distribucion_por_dia": [{"dia": d, "bloques": n} for d, n in by_day.items()],
    }
