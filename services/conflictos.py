from collections import defaultdict

from sqlalchemy.orm import Session

from models import TeacherAvailability, ScheduleEntry, Subject


def _franjas_disponibles(db: Session, profesor_id: int) -> set:
    franjas = set()
    for d in db.query(TeacherAvailability).filter(TeacherAvailability.profesor_id == profesor_id):
        for h in range(d.hora_inicio.hour, d.hora_fin.hour):
            franjas.add((d.dia_semana, h))
    return franjas


def _agrupar_cruces(horarios, clave, tipo, etiqueta):
    grupos = defaultdict(list)
    for h in horarios:
        grupos[clave(h)].append(h)
    conflictos = []
    for (entidad, dia, hora), bloques in grupos.items():
        if len(bloques) > 1:
            conflictos.append(
                {
                    "tipo": tipo,
                    "descripcion": f"{etiqueta} {entidad} tiene {len(bloques)} clases el {dia} a las {hora:02d}:00",
                    "horario_ids": sorted(b.id for b in bloques),
                }
            )
    return conflictos


def detectar_conflictos(db: Session) -> list:
    horarios = db.query(ScheduleEntry).all()
    conflictos = []

    conflictos += _agrupar_cruces(
        horarios,
        lambda h: (h.subject.teacher.nombre, h.dia_semana, h.hora_inicio.hour),
        "cruce_profesor",
        "El profesor",
    )
    conflictos += _agrupar_cruces(
        horarios,
        lambda h: (h.classroom.nombre, h.dia_semana, h.hora_inicio.hour),
        "cruce_aula",
        "El aula",
    )
    conflictos += _agrupar_cruces(
        horarios,
        lambda h: (h.subject.group.nombre, h.dia_semana, h.hora_inicio.hour),
        "cruce_grupo",
        "El grupo",
    )

    cache_disp = {}
    for h in horarios:
        if h.subject.group.num_estudiantes > h.classroom.aforo:
            conflictos.append(
                {
                    "tipo": "sobrecupo",
                    "descripcion": (
                        f"{h.subject.nombre}: el grupo {h.subject.group.nombre} "
                        f"({h.subject.group.num_estudiantes}) no cabe en {h.classroom.nombre} (aforo {h.classroom.aforo})"
                    ),
                    "horario_ids": [h.id],
                }
            )

        pid = h.subject.profesor_id
        if pid not in cache_disp:
            cache_disp[pid] = _franjas_disponibles(db, pid)
        if (h.dia_semana, h.hora_inicio.hour) not in cache_disp[pid]:
            conflictos.append(
                {
                    "tipo": "fuera_de_disponibilidad",
                    "descripcion": (
                        f"{h.subject.teacher.nombre} no está disponible el {h.dia_semana} "
                        f"a las {h.hora_inicio.hour:02d}:00 ({h.subject.nombre})"
                    ),
                    "horario_ids": [h.id],
                }
            )

    # Intensidad horaria: bloques programados vs. requeridos por materia
    programados = defaultdict(list)
    for h in horarios:
        programados[h.materia_id].append(h.id)
    for m in db.query(Subject).all():
        ids = programados.get(m.id, [])
        if len(ids) != m.intensidad_horaria:
            conflictos.append(
                {
                    "tipo": "intensidad_incorrecta",
                    "descripcion": (
                        f"{m.nombre} ({m.group.nombre}) requiere {m.intensidad_horaria} h "
                        f"y tiene {len(ids)} programadas"
                    ),
                    "horario_ids": sorted(ids),
                }
            )

    return conflictos
