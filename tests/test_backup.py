from datetime import timedelta

from fastapi.testclient import TestClient

from main import app
from services.class_changes import WEEKDAY_INDEX, today
from services.users import TEACHER_PASSWORD
from tests.conftest import STUDENT


def login(email: str, password: str) -> TestClient:
    r = TestClient(app).post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})


def my_data(client):
    """A small "real" faculty: one teacher, one classroom, one group, one subject, its schedule and a cancellation."""
    teacher = client.post("/teachers", json={"nombre": "Profe Real", "email": "real@ucc.edu.co"}).json()
    for day in ["Lunes", "Martes"]:
        client.post("/availability", json={"profesor_id": teacher["id"], "dia_semana": day, "hora_inicio": "08:00:00", "hora_fin": "12:00:00"})
    client.post("/classrooms", json={"nombre": "Aula Real", "aforo": 40})
    group = client.post("/groups", json={"nombre": "Grupo Real", "num_estudiantes": 25}).json()
    client.post("/subjects", json={"nombre": "Materia Real", "intensidad_horaria": 2, "grupo_id": group["id"], "profesor_id": teacher["id"]})
    assert client.post("/schedules/generate").status_code == 200

    entry = client.get("/schedules").json()[0]
    day = today()
    while day.weekday() != WEEKDAY_INDEX[entry["dia_semana"]]:
        day += timedelta(days=1)
    prof = login("real@ucc.edu.co", TEACHER_PASSWORD)
    assert prof.post(f"/schedules/{entry['id']}/cancellations", json={"fecha": day.isoformat(), "motivo": "Congreso"}).status_code == 200
    prof.post("/auth/change-password", json={"actual": TEACHER_PASSWORD, "nueva": "claveDelProfe1"})

    student_id = next(u["id"] for u in client.get("/users").json() if u["email"] == STUDENT["email"])
    client.patch(f"/users/{student_id}/group", json={"grupo_id": group["id"]})
    return teacher, group, entry


def test_loading_the_demo_keeps_a_copy_and_restores_everything(client):
    teacher, group, entry = my_data(client)
    before = {path: client.get(path).json() for path in ["/teachers", "/classrooms", "/groups", "/subjects", "/schedules", "/cancellations"]}

    r = client.post("/seed?reset=true")
    assert r.status_code == 200
    assert r.json()["respaldo"]["existe"] is True
    assert r.json()["respaldo"]["resumen"]["profesores"] == 1
    assert all(t["email"] != "real@ucc.edu.co" for t in client.get("/teachers").json())

    # A second demo on top of the demo must not overwrite the copy of the real data
    client.post("/seed?reset=true&dataset=faculty")
    assert client.get("/seed/backup").json()["resumen"]["materias"] == 1

    restored = client.post("/seed/restore")
    assert restored.status_code == 200
    for path, rows in before.items():
        assert client.get(path).json() == rows, path

    # The teacher's account comes back with the password they had set; the student is in their group again
    login("real@ucc.edu.co", "claveDelProfe1")
    student = login(STUDENT["email"], STUDENT["password"])
    assert student.get("/auth/me").json()["grupo_id"] == group["id"]
    assert [e["id"] for e in student.get("/schedules").json()] == [e["id"] for e in before["/schedules"]]

    # No copy left, and new rows still get fresh ids
    assert client.get("/seed/backup").json() == {"existe": False}
    assert client.post("/seed/restore").status_code == 404
    new = client.post("/teachers", json={"nombre": "Otro", "email": "otro@ucc.edu.co"}).json()
    assert new["id"] > teacher["id"]


def test_the_copy_can_be_discarded(client):
    my_data(client)
    client.post("/seed?reset=true")
    assert client.delete("/seed/backup").status_code == 200
    assert client.get("/seed/backup").json() == {"existe": False}
    assert client.post("/seed/restore").status_code == 404


def test_an_empty_database_has_nothing_to_keep(client):
    assert client.post("/seed").status_code == 200
    assert client.get("/seed/backup").json() == {"existe": False}


def test_only_administrators_restore(client, reader_client):
    my_data(client)
    client.post("/seed?reset=true")
    assert reader_client.post("/seed/restore").status_code == 403
    assert reader_client.delete("/seed/backup").status_code == 403
