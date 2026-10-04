from datetime import time

from sqlalchemy.orm import Session

from models import Classroom, TeacherAvailability, StudentGroup, ScheduleEntry, Subject, Teacher

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


def has_data(db: Session) -> bool:
    return any(db.query(m).first() for m in (Teacher, Classroom, StudentGroup, Subject))


def delete_all(db: Session) -> None:
    # Order matters: tables that depend on others go first
    for model in (ScheduleEntry, Subject, TeacherAvailability, StudentGroup, Classroom, Teacher):
        db.query(model).delete()
    db.commit()


def load_demo_data(db: Session) -> dict:
    teachers = [
        Teacher(nombre="Carlos Mendoza", email="carlos.mendoza@ucc.edu.co"),
        Teacher(nombre="Laura Giraldo", email="laura.giraldo@ucc.edu.co"),
        Teacher(nombre="Andrés Ruiz", email="andres.ruiz@ucc.edu.co"),
        Teacher(nombre="Marcela Torres", email="marcela.torres@ucc.edu.co"),
        Teacher(nombre="Julián Parra", email="julian.parra@ucc.edu.co"),
    ]
    classrooms = [
        Classroom(nombre="Aula 101", aforo=40),
        Classroom(nombre="Aula 102", aforo=30),
        Classroom(nombre="Laboratorio de Sistemas", aforo=35),
        Classroom(nombre="Sala B", aforo=25),
    ]
    groups = [
        StudentGroup(nombre="7A", num_estudiantes=30),
        StudentGroup(nombre="7B", num_estudiantes=28),
        StudentGroup(nombre="5A", num_estudiantes=35),
    ]
    db.add_all(teachers + classrooms + groups)
    db.flush()  # assigns the ids without closing the transaction

    t = {i: teachers[i].id for i in range(5)}
    g = {grp.nombre: grp.id for grp in groups}

    # (teacher, days, start_hour, end_hour)
    availabilities = [
        (0, WEEKDAYS, 7, 13),
        (1, WEEKDAYS, 8, 14),
        (2, ["Lunes", "Martes", "Miércoles", "Jueves"], 10, 18),
        (3, WEEKDAYS, 6, 12),
        (4, ["Martes", "Miércoles", "Jueves", "Viernes"], 14, 20),
    ]
    for idx, days, start, end in availabilities:
        for day in days:
            db.add(
                TeacherAvailability(
                    profesor_id=t[idx], dia_semana=day, hora_inicio=time(start), hora_fin=time(end)
                )
            )

    subjects = [
        ("Programación Orientada a la Web", 4, "7A", 0),
        ("Bases de Datos", 3, "7A", 1),
        ("Ingeniería de Software", 3, "7B", 2),
        ("Inteligencia Artificial", 3, "7B", 0),
        ("Estructuras de Datos", 3, "5A", 3),
        ("Redes de Computadores", 2, "5A", 4),
        ("Cálculo Diferencial", 2, "7A", 3),
    ]
    for name, hours, group, teacher in subjects:
        db.add(Subject(nombre=name, intensidad_horaria=hours, grupo_id=g[group], profesor_id=t[teacher]))

    db.commit()
    return {
        "profesores": len(teachers),
        "aulas": len(classrooms),
        "grupos": len(groups),
        "materias": len(subjects),
        "horas_semanales": sum(s[1] for s in subjects),
    }
