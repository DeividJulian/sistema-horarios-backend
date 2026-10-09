from datetime import time

from sqlalchemy.orm import Session

from models import Cancellation, Classroom, Notification, TeacherAvailability, StudentGroup, ScheduleEntry, Subject, Teacher, User
from services.csp import shift_range

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


def has_data(db: Session) -> bool:
    return any(db.query(m).first() for m in (Teacher, Classroom, StudentGroup, Subject))


def delete_all(db: Session) -> None:
    # Order matters: tables that depend on others go first
    for model in (Cancellation, Notification, ScheduleEntry, Subject, TeacherAvailability, StudentGroup, Classroom, Teacher):
        db.query(model).delete()
    # Teacher accounts are created again for the new teachers; students lose their (deleted) group
    db.query(User).filter(User.rol == "profesor").delete()
    db.query(User).filter(User.grupo_id.isnot(None)).update({User.grupo_id: None})
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


# ---------------------------------------------------------------------------
# Faculty data: 8 semesters of Software Engineering, each group with its shift
# ---------------------------------------------------------------------------
# (name, capacity, room type)
FACULTY_CLASSROOMS = [
    ("Sala de informática 2", 40, "informatica"),
    ("Sala de informática 6", 40, "informatica"),
    ("Aula 504B", 45, "general"),
    ("Aula 301", 42, "general"),
    ("Aula 302", 42, "general"),
    ("Aula 303", 42, "general"),
    ("Aula 401", 42, "general"),
    ("Laboratorio de Física", 40, "laboratorio"),
]

# Subjects that need a special room; the rest can use any classroom
FACULTY_ROOM_NEEDS = {
    "informatica": {
        "Fundamentos de Programación", "Programación Orientada a Objetos", "Estructuras de Datos",
        "Bases de Datos I", "Bases de Datos II", "Desarrollo Web", "Desarrollo Móvil",
        "Programación Orientada a la Web", "Inteligencia de Negocios y Minería de Datos",
    },
    "laboratorio": {"Física Mecánica", "Física Electromagnética"},
}

# key -> (name, email). Fictitious names: replace them with the real ones if you want.
FACULTY_TEACHERS = {
    "mat": ("Patricia Enríquez", "patricia.enriquez@ucc.edu.co"),
    "prog": ("Fernando Salas", "fernando.salas@ucc.edu.co"),
    "dis": ("Mónica Játiva", "monica.jativa@ucc.edu.co"),
    "fis": ("Raúl Delgado", "raul.delgado@ucc.edu.co"),
    "log": ("Sandra Chamorro", "sandra.chamorro@ucc.edu.co"),
    "com": ("Camilo Erazo", "camilo.erazo@ucc.edu.co"),
    "bd": ("Diana Insuasty", "diana.insuasty@ucc.edu.co"),
    "arq": ("Hernán Bolaños", "hernan.bolanos@ucc.edu.co"),
    "web": ("Lucía Montenegro", "lucia.montenegro@ucc.edu.co"),
    "ges": ("Andrés Villota", "andres.villota@ucc.edu.co"),
    "ia": ("Jorge Pantoja", "jorge.pantoja@ucc.edu.co"),
    "inv": ("Natalia Rosero", "natalia.rosero@ucc.edu.co"),
    "leg": ("Gabriel Cabrera", "gabriel.cabrera@ucc.edu.co"),
    "pow": ("Ricardo Benavides", "ricardo.benavides@ucc.edu.co"),
    "emb": ("Iván Burgos", "ivan.burgos@ucc.edu.co"),
    "comp": ("Gustavo Mejía", "gustavo.mejia@ucc.edu.co"),
    "neg": ("Cristian Ortiz", "cristian.ortiz@ucc.edu.co"),
    "tg": ("Luis Chávez", "luis.chavez@ucc.edu.co"),
}

# (group, shift, students, [(subject, weekly hours, teacher key)])
# Odd semesters in the morning, even ones in the afternoon and the last two in the evening.
SEMESTERS = [
    ("Ingeniería de Software 1", "manana", 40, [
        ("Introducción a la Ingeniería de Software", 2, "dis"), ("Cálculo Diferencial", 4, "mat"),
        ("Lógica y Matemáticas Discretas", 3, "log"), ("Fundamentos de Programación", 4, "prog"),
        ("Comunicación Oral y Escrita", 2, "com")]),
    ("Ingeniería de Software 2", "tarde", 40, [
        ("Cálculo Integral", 4, "mat"), ("Programación Orientada a Objetos", 4, "prog"),
        ("Física Mecánica", 3, "fis"), ("Álgebra Lineal", 3, "log"), ("Ética y Ciudadanía", 2, "com")]),
    ("Ingeniería de Software 3", "manana", 40, [
        ("Estructuras de Datos", 4, "prog"), ("Cálculo Vectorial", 3, "mat"),
        ("Física Electromagnética", 3, "fis"), ("Bases de Datos I", 4, "bd"),
        ("Probabilidad y Estadística", 3, "log")]),
    ("Ingeniería de Software 4", "tarde", 40, [
        ("Bases de Datos II", 3, "bd"), ("Análisis y Diseño de Software", 4, "dis"),
        ("Arquitectura de Computadores", 3, "arq"), ("Métodos Numéricos", 3, "mat"),
        ("Sistemas Operativos", 3, "arq")]),
    ("Ingeniería de Software 5", "manana", 40, [
        ("Ingeniería de Requisitos", 3, "dis"), ("Redes de Computadores", 3, "arq"),
        ("Desarrollo Web", 4, "web"), ("Algoritmos Avanzados", 3, "prog"),
        ("Gestión de Proyectos de Software", 2, "ges")]),
    ("Ingeniería de Software 6", "tarde", 40, [
        ("Arquitectura de Software", 3, "web"), ("Desarrollo Móvil", 4, "web"),
        ("Inteligencia Artificial", 3, "ia"), ("Seguridad Informática", 3, "ia"),
        ("Electiva I", 2, "ges"), ("Investigación Aplicada", 2, "inv")]),
    # Seventh semester: subjects and weekly hours of the real published schedule
    ("Ingeniería de Software 7", "noche", 40, [
        ("Aspectos Legales y Éticos para Ingeniería", 2, "leg"), ("Metodologías de Software Colaborativo", 2, "leg"),
        ("Programación Orientada a la Web", 3, "pow"), ("Programación de Sistemas Embebidos y de Tiempo Real", 3, "emb"),
        ("Compiladores", 2, "comp"), ("Inteligencia de Negocios y Minería de Datos", 2, "neg"),
        ("Pruebas y Mantenimiento de Software", 2, "leg"), ("Construcción del Trabajo de Grado", 3, "tg")]),
    ("Ingeniería de Software 8", "noche", 40, [
        ("Trabajo de Grado II", 3, "tg"), ("Electiva II", 2, "inv"), ("Gerencia de Proyectos de TI", 2, "ges"),
        ("Computación en la Nube", 3, "ia"), ("Práctica Profesional", 3, "inv"),
        ("Emprendimiento Tecnológico", 2, "com")]),
]


def load_faculty_data(db: Session) -> dict:
    """Loads the 8 semesters. Each teacher is available during the shifts of the groups they teach."""
    classrooms = [Classroom(nombre=n, aforo=c, tipo=t) for n, c, t in FACULTY_CLASSROOMS]
    teachers = {k: Teacher(nombre=n, email=e) for k, (n, e) in FACULTY_TEACHERS.items()}
    groups = [StudentGroup(nombre=n, num_estudiantes=st, jornada=sh) for n, sh, st, _ in SEMESTERS]
    db.add_all(classrooms + list(teachers.values()) + groups)
    db.flush()

    shifts_of = {k: set() for k in teachers}
    total_subjects = total_hours = 0
    for group, (_, shift, _, subjects) in zip(groups, SEMESTERS):
        for name, hours, key in subjects:
            room = next((t for t, names in FACULTY_ROOM_NEEDS.items() if name in names), "cualquiera")
            db.add(
                Subject(
                    nombre=name, intensidad_horaria=hours, grupo_id=group.id, profesor_id=teachers[key].id, tipo_aula=room
                )
            )
            shifts_of[key].add(shift)
            total_subjects += 1
            total_hours += hours

    for key, shifts in shifts_of.items():
        for shift in sorted(shifts):
            start, end = shift_range(shift)
            for day in WEEKDAYS:
                db.add(
                    TeacherAvailability(
                        profesor_id=teachers[key].id, dia_semana=day, hora_inicio=time(start), hora_fin=time(end)
                    )
                )
    db.commit()
    return {
        "profesores": len(teachers),
        "aulas": len(classrooms),
        "grupos": len(groups),
        "materias": total_subjects,
        "horas_semanales": total_hours,
    }
