from datetime import time

from models import Classroom, ScheduleEntry, StudentGroup, Subject, Teacher, TeacherAvailability
from services import csp


def _scenario(db, required="informatica", classrooms=(("Aula 101", 40, "general"), ("Sala 2", 40, "informatica"))):
    db.add_all([Classroom(nombre=n, aforo=a, tipo=t) for n, a, t in classrooms])
    group = StudentGroup(nombre="G1", num_estudiantes=30)
    teacher = Teacher(nombre="Prof", email="prof@ucc.edu.co")
    db.add_all([group, teacher])
    db.flush()
    for day in ["Lunes", "Martes", "Miércoles"]:
        db.add(TeacherAvailability(profesor_id=teacher.id, dia_semana=day, hora_inicio=time(8), hora_fin=time(10)))
    db.add(Subject(nombre="Programación", intensidad_horaria=3, grupo_id=group.id, profesor_id=teacher.id, tipo_aula=required))
    db.commit()


def test_classroom_type_defaults_to_general_and_can_be_edited(client):
    c = client.post("/classrooms", json={"nombre": "Aula 1", "aforo": 30}).json()
    assert c["tipo"] == "general"
    r = client.put(f"/classrooms/{c['id']}", json={"nombre": "Aula 1", "aforo": 30, "tipo": "laboratorio"})
    assert r.json()["tipo"] == "laboratorio"
    assert client.post("/classrooms", json={"nombre": "Aula 2", "aforo": 30, "tipo": "cocina"}).status_code == 422


def test_subject_room_type_defaults_to_any(client):
    t = client.post("/teachers", json={"nombre": "Ana", "email": "ana@ucc.edu.co"}).json()
    g = client.post("/groups", json={"nombre": "7A", "num_estudiantes": 20}).json()
    s = client.post("/subjects", json={"nombre": "Redes", "intensidad_horaria": 2, "grupo_id": g["id"], "profesor_id": t["id"]}).json()
    assert s["tipo_aula"] == "cualquiera"
    r = client.put(
        f"/subjects/{s['id']}",
        json={"nombre": "Redes", "intensidad_horaria": 2, "grupo_id": g["id"], "profesor_id": t["id"], "tipo_aula": "informatica"},
    )
    assert r.json()["tipo_aula"] == "informatica"


def test_subject_that_needs_a_computer_room_only_uses_computer_rooms(db):
    _scenario(db)
    success, assignments, _ = csp.compute_assignments(db)
    assert success
    assert {c.nombre for _, c, _, _ in assignments} == {"Sala 2"}


def test_explains_when_no_classroom_has_the_required_type(db):
    _scenario(db, required="laboratorio")
    success, _, message = csp.compute_assignments(db)
    assert not success
    assert "Ninguna aula sirve para 'Programación'" in message and "un laboratorio" in message


def test_detects_a_class_in_the_wrong_room_type(client, db):
    _scenario(db)
    subject = db.query(Subject).first()
    general = db.query(Classroom).filter(Classroom.tipo == "general").first()
    db.add(ScheduleEntry(materia_id=subject.id, aula_id=general.id, dia_semana="Lunes", hora_inicio=time(8), hora_fin=time(9)))
    db.commit()
    conflicts = client.get("/conflicts").json()["conflictos"]
    assert any(c["tipo"] == "tipo_de_aula" and "sala de informática" in c["descripcion"] for c in conflicts)


def test_faculty_seed_puts_programming_in_computer_rooms(client):
    client.post("/seed?dataset=faculty")
    assert client.post("/schedules/generate").status_code == 200
    rooms = {c["id"]: c for c in client.get("/classrooms").json()}
    subjects = {s["id"]: s for s in client.get("/subjects").json()}
    for block in client.get("/schedules").json():
        required = subjects[block["materia_id"]]["tipo_aula"]
        if required != "cualquiera":
            assert rooms[block["aula_id"]]["tipo"] == required
    assert client.get("/conflicts").json()["hay_conflictos"] is False
