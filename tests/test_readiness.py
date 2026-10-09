from datetime import time

from models import Classroom, StudentGroup, Subject, Teacher, TeacherAvailability


def test_empty_database_lists_every_missing_piece(client):
    r = client.get("/diagnostics").json()
    assert r["listo"] is False
    assert {p["tipo"] for p in r["problemas"]} == {"sin_aulas", "sin_grupos", "sin_profesores", "sin_materias"}


def test_demo_data_is_ready(client):
    client.post("/seed")
    assert client.get("/diagnostics").json() == {"listo": True, "problemas": []}


def test_faculty_data_is_ready(client):
    client.post("/seed?dataset=faculty")
    assert client.get("/diagnostics").json()["listo"] is True


def _base(db, shift="todo", students=30, slot=None, hours=3, room="cualquiera"):
    db.add(Classroom(nombre="A1", aforo=40))
    group = StudentGroup(nombre="7A", num_estudiantes=students, jornada=shift)
    teacher = Teacher(nombre="Juan Pérez", email="juan@ucc.edu.co")
    db.add_all([group, teacher])
    db.flush()
    if slot:
        db.add(TeacherAvailability(profesor_id=teacher.id, dia_semana="Lunes", hora_inicio=time(slot[0]), hora_fin=time(slot[1])))
    db.add(Subject(nombre="Web", intensidad_horaria=hours, grupo_id=group.id, profesor_id=teacher.id, tipo_aula=room))
    db.commit()
    return teacher


def test_teacher_without_availability_points_to_the_teacher(client, db):
    teacher = _base(db)
    problems = client.get("/diagnostics").json()["problemas"]
    assert problems == [{
        "tipo": "sin_disponibilidad",
        "mensaje": "Juan Pérez no tiene disponibilidad. Marca las horas en que puede dar clase.",
        "seccion": "profesores",
        "profesor_id": teacher.id,
    }]


def test_availability_outside_the_group_shift_is_explained_with_am_pm(client, db):
    _base(db, shift="noche", slot=(8, 12))
    message = client.get("/diagnostics").json()["problemas"][0]["mensaje"]
    assert "0 h disponibles en la noche (6:00 p. m. a 10:00 p. m.)" in message and "'Web' necesita 3 h" in message


def test_missing_room_type_and_group_without_space(client, db):
    _base(db, slot=(8, 20), hours=3, room="laboratorio")
    kinds = {p["tipo"] for p in client.get("/diagnostics").json()["problemas"]}
    assert "sin_aula_adecuada" in kinds


def test_group_with_more_hours_than_its_shift_allows(client, db):
    _base(db, shift="noche", slot=(18, 22), hours=5)
    db.add(Subject(nombre="Otra", intensidad_horaria=5, grupo_id=1, profesor_id=1))
    for i in range(3):
        db.add(Subject(nombre=f"Extra {i}", intensidad_horaria=5, grupo_id=1, profesor_id=1))
    db.commit()
    problems = client.get("/diagnostics").json()["problemas"]
    assert any(p["tipo"] == "grupo_sin_espacio" and "caben máximo 20 h" in p["mensaje"] for p in problems)
