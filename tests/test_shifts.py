import time as clock
from datetime import time

from models import Classroom, ScheduleEntry, StudentGroup, Subject, Teacher, TeacherAvailability
from services import csp

WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


def _scenario(db, shift, slot=(7, 22), weekly_hours=3):
    classroom = Classroom(nombre="A1", aforo=40)
    group = StudentGroup(nombre="G1", num_estudiantes=30, jornada=shift)
    teacher = Teacher(nombre="Prof", email="prof@ucc.edu.co")
    db.add_all([classroom, group, teacher])
    db.flush()
    for day in WEEKDAYS:
        db.add(TeacherAvailability(profesor_id=teacher.id, dia_semana=day, hora_inicio=time(slot[0]), hora_fin=time(slot[1])))
    db.add(Subject(nombre="M1", intensidad_horaria=weekly_hours, grupo_id=group.id, profesor_id=teacher.id))
    db.commit()
    return group


def _clear(db):
    for model in (ScheduleEntry, Subject, TeacherAvailability, StudentGroup, Classroom, Teacher):
        db.query(model).delete()
    db.commit()


def test_new_group_has_no_shift_restriction(client):
    r = client.post("/groups", json={"nombre": "G1", "num_estudiantes": 30})
    assert r.status_code == 200 and r.json()["jornada"] == "todo"


def test_create_and_edit_group_shift(client):
    g = client.post("/groups", json={"nombre": "G1", "num_estudiantes": 30, "jornada": "noche"}).json()
    assert g["jornada"] == "noche"
    r = client.put(f"/groups/{g['id']}", json={"nombre": "G1", "num_estudiantes": 30, "jornada": "tarde"})
    assert r.json()["jornada"] == "tarde"


def test_invalid_shift_returns_422(client):
    r = client.post("/groups", json={"nombre": "G1", "num_estudiantes": 30, "jornada": "madrugada"})
    assert r.status_code == 422


def test_classes_stay_inside_the_group_shift(db):
    for shift, (start, end) in {"manana": (7, 13), "tarde": (13, 18), "noche": (18, 22)}.items():
        _clear(db)
        _scenario(db, shift)  # the teacher is available all day
        success, assignments, _ = csp.compute_assignments(db)
        assert success, shift
        assert all(start <= h.hour < end for _, _, _, h in assignments), shift


def test_teacher_only_available_outside_the_shift_explains_the_problem(db):
    _scenario(db, "noche", slot=(8, 12))
    success, _, message = csp.compute_assignments(db)
    assert not success
    assert "0 h disponibles en la noche" in message and "jornada del grupo" in message


def test_detects_class_outside_the_shift(client, db):
    _scenario(db, "manana")
    subject = db.query(Subject).first()
    classroom = db.query(Classroom).first()
    db.add(ScheduleEntry(materia_id=subject.id, aula_id=classroom.id, dia_semana="Lunes", hora_inicio=time(19), hora_fin=time(20)))
    db.commit()
    kinds = [c["tipo"] for c in client.get("/conflicts").json()["conflictos"]]
    assert "fuera_de_jornada" in kinds


def test_cannot_move_a_block_outside_the_shift(client, db):
    _scenario(db, "manana")
    assert client.post("/schedules/generate").status_code == 200
    block = client.get("/schedules").json()[0]
    r = client.put(f"/schedules/{block['id']}", json={"dia_semana": "Viernes", "hora_inicio": "20:00:00"})
    assert r.status_code == 409 and "la mañana" in r.json()["detail"]


def test_evening_blocks_can_start_at_21(client, db):
    _scenario(db, "noche", weekly_hours=1)
    assert client.post("/schedules/generate").status_code == 200
    block = client.get("/schedules").json()[0]
    r = client.put(f"/schedules/{block['id']}", json={"dia_semana": "Viernes", "hora_inicio": "21:00:00"})
    assert r.status_code == 200 and r.json()["hora_fin"] == "22:00:00"


def test_faculty_seed_generates_a_schedule_without_conflicts(client):
    r = client.post("/seed?dataset=faculty")
    assert r.status_code == 200
    assert r.json()["resumen"] == {"profesores": 18, "aulas": 8, "grupos": 8, "materias": 45, "horas_semanales": 130}
    groups = client.get("/groups").json()
    assert [g["jornada"] for g in groups] == ["manana", "tarde", "manana", "tarde", "manana", "tarde", "noche", "noche"]
    started = clock.perf_counter()
    assert client.post("/schedules/generate").json()["total_bloques"] == 130
    assert clock.perf_counter() - started < csp.TIME_LIMIT_SECONDS
    assert client.get("/conflicts").json()["hay_conflictos"] is False


def test_seed_with_invalid_dataset(client):
    assert client.post("/seed?dataset=otro").status_code == 422
