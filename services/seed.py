from datetime import time

from sqlalchemy.orm import Session

from models import Aula, DisponibilidadProfesor, Grupo, Horario, Materia, Profesor

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


def hay_datos(db: Session) -> bool:
    return any(db.query(m).first() for m in (Profesor, Aula, Grupo, Materia))


def borrar_todo(db: Session) -> None:
    # Orden: primero las tablas que dependen de otras
    for modelo in (Horario, Materia, DisponibilidadProfesor, Grupo, Aula, Profesor):
        db.query(modelo).delete()
    db.commit()


def cargar_datos_demo(db: Session) -> dict:
    profesores = [
        Profesor(nombre="Carlos Mendoza", email="carlos.mendoza@ucc.edu.co"),
        Profesor(nombre="Laura Giraldo", email="laura.giraldo@ucc.edu.co"),
        Profesor(nombre="Andrés Ruiz", email="andres.ruiz@ucc.edu.co"),
        Profesor(nombre="Marcela Torres", email="marcela.torres@ucc.edu.co"),
        Profesor(nombre="Julián Parra", email="julian.parra@ucc.edu.co"),
    ]
    aulas = [
        Aula(nombre="Aula 101", aforo=40),
        Aula(nombre="Aula 102", aforo=30),
        Aula(nombre="Laboratorio de Sistemas", aforo=35),
        Aula(nombre="Sala B", aforo=25),
    ]
    grupos = [
        Grupo(nombre="7A", num_estudiantes=30),
        Grupo(nombre="7B", num_estudiantes=28),
        Grupo(nombre="5A", num_estudiantes=35),
    ]
    db.add_all(profesores + aulas + grupos)
    db.flush()  # asigna los ids sin cerrar la transacción

    p = {i: profesores[i].id for i in range(5)}
    g = {n.nombre: n.id for n in grupos}

    # (profesor, días, hora_inicio, hora_fin)
    disponibilidades = [
        (0, DIAS, 7, 13),
        (1, DIAS, 8, 14),
        (2, ["Lunes", "Martes", "Miércoles", "Jueves"], 10, 18),
        (3, DIAS, 6, 12),
        (4, ["Martes", "Miércoles", "Jueves", "Viernes"], 14, 20),
    ]
    for idx, dias, ini, fin in disponibilidades:
        for dia in dias:
            db.add(
                DisponibilidadProfesor(
                    profesor_id=p[idx], dia_semana=dia, hora_inicio=time(ini), hora_fin=time(fin)
                )
            )

    materias = [
        ("Programación Orientada a la Web", 4, "7A", 0),
        ("Bases de Datos", 3, "7A", 1),
        ("Ingeniería de Software", 3, "7B", 2),
        ("Inteligencia Artificial", 3, "7B", 0),
        ("Estructuras de Datos", 3, "5A", 3),
        ("Redes de Computadores", 2, "5A", 4),
        ("Cálculo Diferencial", 2, "7A", 3),
    ]
    for nombre, horas, grupo, prof in materias:
        db.add(Materia(nombre=nombre, intensidad_horaria=horas, grupo_id=g[grupo], profesor_id=p[prof]))

    db.commit()
    return {
        "profesores": len(profesores),
        "aulas": len(aulas),
        "grupos": len(grupos),
        "materias": len(materias),
        "horas_semanales": sum(m[1] for m in materias),
    }
