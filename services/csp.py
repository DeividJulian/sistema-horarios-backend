from datetime import time

from sqlalchemy.orm import Session

from models import Aula, DisponibilidadProfesor, Grupo, Materia

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

# Un grupo no puede tener mas de este numero de horas de clase en un mismo dia
MAX_HORAS_DIA_GRUPO = 4

# Rango de horas de inicio posibles (coincide con la validacion de schemas.py)
HORA_MIN = 6
HORA_MAX = 21


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

    # Heuristica de grado: cuantas otras materias comparten profesor o grupo con cada una.
    # Las materias con mas "vecinas" generan mas cruces posibles, asi que se colocan antes.
    def grado(m):
        return sum(
            1
            for o in materias
            if o.id != m.id and (o.profesor_id == m.profesor_id or o.grupo_id == m.grupo_id)
        )

    # Ordenar: primero las mas restringidas (pocas franjas por hora a ubicar) y, a igualdad, las de mayor grado
    materias_ordenadas = sorted(
        materias,
        key=lambda m: (
            len(disponibilidad_por_profesor.get(m.profesor_id, set())) / m.intensidad_horaria,
            -grado(m),
            m.id,
        ),
    )

    ocupado_profesor = set()
    ocupado_aula = set()
    ocupado_grupo = set()
    horas_grupo_dia = {}
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

        def tiene_clase(entidad_id, ocupado, dia, h):
            return 0 <= h <= 23 and (entidad_id, dia, time(hour=h)) in ocupado

        def costo_franja(entidad_id, ocupado, dia, hora):
            """0 si la clase queda pegada a otra, 1 si el dia estaba libre, 2 si abre una franja muerta."""
            h = hora.hour
            if tiene_clase(entidad_id, ocupado, dia, h - 1) or tiene_clase(entidad_id, ocupado, dia, h + 1):
                return 0
            if any(tiene_clase(entidad_id, ocupado, dia, x) for x in range(HORA_MIN, HORA_MAX)):
                return 2
            return 1

        def clave_orden(slot):
            dia, hora = slot
            penalizacion = costo_franja(materia.profesor_id, ocupado_profesor, dia, hora) + costo_franja(
                materia.grupo_id, ocupado_grupo, dia, hora
            )
            return (penalizacion, _orden_dia(dia), hora)

        # Se prueban primero las franjas que no dejan huecos; el backtracking sigue siendo completo
        candidatos = [
            (dia, hora, aula)
            for (dia, hora) in sorted(slots_profesor, key=clave_orden)
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
                if horas_grupo_dia.get((materia.grupo_id, dia), 0) >= MAX_HORAS_DIA_GRUPO:
                    continue
                clave_prof = (materia.profesor_id, dia, hora)
                clave_aula = (aula.id, dia, hora)
                clave_grupo = (materia.grupo_id, dia, hora)
                if clave_prof in ocupado_profesor or clave_aula in ocupado_aula or clave_grupo in ocupado_grupo:
                    continue

                ocupado_profesor.add(clave_prof)
                ocupado_aula.add(clave_aula)
                ocupado_grupo.add(clave_grupo)
                horas_grupo_dia[(materia.grupo_id, dia)] = horas_grupo_dia.get((materia.grupo_id, dia), 0) + 1
                resultado.append((materia, aula, dia, hora))
                dias_usados.add(dia)

                if asignar_bloques(pos + 1, dias_usados, i + 1):
                    return True

                ocupado_profesor.discard(clave_prof)
                ocupado_aula.discard(clave_aula)
                ocupado_grupo.discard(clave_grupo)
                horas_grupo_dia[(materia.grupo_id, dia)] -= 1
                resultado.pop()
                dias_usados.discard(dia)
            return False

        return asignar_bloques(0, set(), 0)

    if not asignar_materia(0):
        return False, [], "No fue posible generar un horario sin cruces con los datos actuales. Revisa disponibilidad de profesores o número de aulas disponibles."

    return True, list(resultado), "OK"
