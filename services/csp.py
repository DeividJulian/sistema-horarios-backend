from datetime import time

from sqlalchemy.orm import Session

from models import Aula, DisponibilidadProfesor, Grupo, Materia


def generar_bloques_horarios(hora_inicio: time, hora_fin: time):
    """Convierte un rango de disponibilidad en bloques de 1 hora."""
    bloques = []
    h = hora_inicio.hour
    while h < hora_fin.hour:
        bloques.append(time(hour=h))
        h += 1
    return bloques


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

    # Ordenar: materias cuyo profesor tiene MENOS disponibilidad van primero (más restringido primero)
    materias_ordenadas = sorted(
        materias,
        key=lambda m: len(disponibilidad_por_profesor.get(m.profesor_id, set()))
    )

    ocupado_profesor = set()
    ocupado_aula = set()
    ocupado_grupo = set()
    resultado_final = []

    def backtrack(index):
        if index == len(materias_ordenadas):
            return True

        materia = materias_ordenadas[index]
        grupo = grupos.get(materia.grupo_id)
        if grupo is None:
            return False

        slots_profesor = disponibilidad_por_profesor.get(materia.profesor_id, set())
        aulas_validas = [a for a in aulas if a.aforo >= grupo.num_estudiantes]

        candidatos = [(dia, hora, aula) for (dia, hora) in slots_profesor for aula in aulas_validas]

        asignaciones_materia = []

        def backtrack_bloques(pos, dias_usados):
            if pos == materia.intensidad_horaria:
                return True
            for (dia, hora, aula) in candidatos:
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
                asignaciones_materia.append((materia, aula, dia, hora))
                dias_usados.add(dia)

                if backtrack_bloques(pos + 1, dias_usados):
                    return True

                ocupado_profesor.discard(clave_prof)
                ocupado_aula.discard(clave_aula)
                ocupado_grupo.discard(clave_grupo)
                asignaciones_materia.pop()
                dias_usados.discard(dia)
            return False

        if not backtrack_bloques(0, set()):
            return False

        resultado_final.extend(asignaciones_materia)

        if backtrack(index + 1):
            return True

        # Deshacer si una materia posterior no tiene solución
        for (m, aula, dia, hora) in asignaciones_materia:
            ocupado_profesor.discard((m.profesor_id, dia, hora))
            ocupado_aula.discard((aula.id, dia, hora))
            ocupado_grupo.discard((m.grupo_id, dia, hora))
            resultado_final.remove((m, aula, dia, hora))
        return False

    exito = backtrack(0)

    if not exito:
        return False, [], "No fue posible generar un horario sin cruces con los datos actuales. Revisa disponibilidad de profesores o número de aulas disponibles."

    return True, resultado_final, "OK"
