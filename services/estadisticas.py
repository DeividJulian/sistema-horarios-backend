from collections import defaultdict

from sqlalchemy.orm import Session

from models import Classroom, StudentGroup, ScheduleEntry, Subject, Teacher

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
# 5 días x 15 horas de inicio posibles (6:00 a 20:00)
BLOQUES_POR_SEMANA = 5 * 15


def _pct(parte: float, total: float) -> float:
    return round(100 * parte / total, 1) if total else 0.0


def calcular_estadisticas(db: Session) -> dict:
    horarios = db.query(ScheduleEntry).all()
    materias = db.query(Subject).all()

    requeridas = sum(m.intensidad_horaria for m in materias)
    programadas = len(horarios)
    cumplimiento = _pct(min(programadas, requeridas), requeridas)

    por_aula = defaultdict(int)
    por_profesor = defaultdict(list)
    por_dia = {d: 0 for d in DIAS}
    for h in horarios:
        por_aula[h.aula_id] += 1
        por_profesor[h.subject.profesor_id].append((h.dia_semana, h.hora_inicio.hour))
        por_dia[h.dia_semana] = por_dia.get(h.dia_semana, 0) + 1

    ocupacion_aulas = [
        {
            "aula_id": a.id,
            "aula": a.nombre,
            "aforo": a.aforo,
            "horas_ocupadas": por_aula.get(a.id, 0),
            "ocupacion_pct": _pct(por_aula.get(a.id, 0), BLOQUES_POR_SEMANA),
        }
        for a in db.query(Classroom).all()
    ]

    carga_profesores = []
    for p in db.query(Teacher).all():
        franjas = por_profesor.get(p.id, [])
        muertas = 0
        for dia in DIAS:
            horas = sorted(h for d, h in franjas if d == dia)
            if len(horas) > 1:
                muertas += (horas[-1] - horas[0] + 1) - len(horas)
        carga_profesores.append(
            {
                "profesor_id": p.id,
                "profesor": p.nombre,
                "horas_semanales": len(franjas),
                "dias_con_clase": len({d for d, _ in franjas}),
                "franjas_muertas": muertas,
            }
        )

    return {
        "totales": {
            "profesores": db.query(Teacher).count(),
            "aulas": db.query(Classroom).count(),
            "grupos": db.query(StudentGroup).count(),
            "materias": len(materias),
            "bloques_programados": programadas,
        },
        "cumplimiento": {
            "horas_requeridas": requeridas,
            "horas_programadas": programadas,
            "porcentaje": cumplimiento,
        },
        "ocupacion_aulas": ocupacion_aulas,
        "carga_profesores": carga_profesores,
        "distribucion_por_dia": [{"dia": d, "bloques": n} for d, n in por_dia.items()],
    }
