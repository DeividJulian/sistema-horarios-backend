from datetime import time

from sqlalchemy.orm import Session

from models import Aula, DisponibilidadProfesor, Grupo, Materia

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


def generar_bloques_horarios(hora_inicio: time, hora_fin: time):
    """Convierte un rango de disponibilidad en bloques de 1 hora."""
    bloques = []
    h = hora_inicio.hour
    while h < hora_fin.hour:
        bloques.append(time(hour=h))
        h += 1
    return bloques


def _orden_dia(dia: str) -> int:
    return DIAS.index(dia) if dia in DIAS else len(DIAS)


def calcular_asignaciones(db: Session):
    materias = db.query(Materia).all()
    aulas = db.query(Aula).all()
    grupos = {g.id: g for g in db.query(Grupo).all()}

    if not materias or not aulas:
        return False, [], "No hay materias o aulas registradas."

    # Disponibilidad de cada profesor como conjunto de (dia, hora)
    disponibilidad_por_profesor = {}
    for materia in materias:
        pid = materia.profesor_id
        if pid not in disponibilidad_por_profesor:
            slots = set()
            disponibilidades = db.query(DisponibilidadProfesor).filter(
                DisponibilidadProfesor.profesor_id == pid
            ).all()
            for d in disponibilidades:
                for h in generar_bloques_horarios(d.hora_inicio, d.hora_fin):
                    slots.add((d.dia_semana, h))
            disponibilidad_por_profesor[pid] = slots

    # Ordenar: materias cuyo profesor tiene MENOS disponibilidad van primero (mas restringido primero)
    materias_ordenadas = sorted(
        materias,
        key=lambda m: (len(disponibilidad_por_profesor.get(m.profesor_id, set())), m.id),
    )

    ocupado_profesor = set()
    ocupado_aula = set()
    ocupado_grupo = set()
    resultado = []

    def asignar_materia(index):
        if index == len(materias_ordenadas):
            return True

        materia = materias_ordenadas[index]
        grupo = grupos.get(materia.grupo_id)
        if grupo is None:
            return False

        slots_profesor = disponibilidad_por_profesor.get(materia.profesor_id, set())
        aulas_validas = sorted(
            (a for a in aulas if a.aforo >= grupo.num_estudiantes), key=lambda a: (a.aforo, a.id)
        )
        # Orden determinista: por dia, hora y aula mas ajustada primero
        candidatos = [
            (dia, hora, aula)
            for (dia, hora) in sorted(slots_profesor, key=lambda s: (_orden_dia(s[0]), s[1]))
            for aula in aulas_validas
        ]

        def asignar_bloques(pos, dias_usados, desde):
            if pos == materia.intensidad_horaria:
                # Materia completa: seguir con la siguiente. Si falla, se prueban
                # otras combinaciones de ESTA materia (backtracking real).
                return asignar_materia(index + 1)

            for i in range(desde, len(candidatos)):
                dia, hora, aula = candidatos[i]
                if dia in dias_usados:
                    continue
                clave_prof = (materia.profesor_id, dia, hora)
                clave_aula = (aula.id, dia, hora)
                clave_grupo = (materia.grupo_id, dia, hora)
                if clave_prof in ocupado_profesor or clave_aula in ocupado_aula or clave_grupo in ocupado_grupo:
                    continue

                ocupado_profesor.add(clave_prof)
                ocupado_aula.add(clave_aula)
                ocupado_grupo.add(clave_grupo)
                resultado.append((materia, aula, dia, hora))
                dias_usados.add(dia)

                if asignar_bloques(pos + 1, dias_usados, i + 1):
                    return True

                ocupado_profesor.discard(clave_prof)
                ocupado_aula.discard(clave_aula)
                ocupado_grupo.discard(clave_grupo)
                resultado.pop()
                dias_usados.discard(dia)
            return False

        return asignar_bloques(0, set(), 0)

    if not asignar_materia(0):
        return False, [], "No fue posible generar un horario sin cruces con los datos actuales. Revisa disponibilidad de profesores o número de aulas disponibles."

    return True, list(resultado), "OK"
