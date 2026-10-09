from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from main import app
from services.class_changes import WEEKDAY_INDEX, today
from services.users import TEACHER_PASSWORD
from tests.conftest import STUDENT


def login(email: str, password: str) -> TestClient:
    r = TestClient(app).post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})


def next_date(weekday: str):
    """Next date (today included) that falls on the given weekday."""
    day = today()
    while day.weekday() != WEEKDAY_INDEX[weekday]:
        day += timedelta(days=1)
    return day


@pytest.fixture
def generated(client, demo_data):
    assert client.post("/schedules/generate").status_code == 200
    return client


def teacher_with_entry(admin: TestClient):
    """(teacher, one of their blocks, its subject)."""
    subjects = {s["id"]: s for s in admin.get("/subjects").json()}
    teachers = {t["id"]: t for t in admin.get("/teachers").json()}
    entry = admin.get("/schedules").json()[0]
    subject = subjects[entry["materia_id"]]
    return teachers[subject["profesor_id"]], entry, subject


def test_every_teacher_gets_an_account_with_their_email(generated):
    users = generated.get("/users").json()
    teachers = generated.get("/teachers").json()
    teacher_accounts = {u["email"]: u for u in users if u["rol"] == "profesor"}
    assert {t["email"] for t in teachers} == set(teacher_accounts)
    teacher = teachers[0]
    me = login(teacher["email"], TEACHER_PASSWORD).get("/auth/me").json()
    assert me["rol"] == "profesor" and me["profesor_id"] == teacher["id"]


def test_demo_accounts_cover_every_role(generated):
    accounts = TestClient(app).get("/auth/demo-accounts").json()
    assert [a["rol"] for a in accounts] == ["admin", "profesor", "estudiante", "usuario"]
    for account in accounts:
        login(account["email"], account["password"])


def test_student_only_sees_their_group(generated):
    student = login(STUDENT["email"], STUDENT["password"])
    me = student.get("/auth/me").json()
    assert me["grupo_id"] is not None

    group_subjects = {s["id"] for s in generated.get("/subjects").json() if s["grupo_id"] == me["grupo_id"]}
    mine = student.get("/schedules").json()
    everything = generated.get("/schedules").json()
    assert mine and len(mine) < len(everything)
    assert all(e["materia_id"] in group_subjects for e in mine)

    assert student.get("/statistics").status_code == 403
    assert student.get("/conflicts").status_code == 403
    assert student.post("/schedules/generate").status_code == 403


def test_teacher_cancels_a_class_and_the_group_is_notified(generated):
    teacher, entry, subject = teacher_with_entry(generated)
    prof = login(teacher["email"], TEACHER_PASSWORD)
    day = next_date(entry["dia_semana"])

    r = prof.post(f"/schedules/{entry['id']}/cancellations", json={"fecha": day.isoformat(), "motivo": "Cita médica"})
    assert r.status_code == 200, r.text
    cancellation = r.json()
    assert prof.post(
        f"/schedules/{entry['id']}/cancellations", json={"fecha": day.isoformat(), "motivo": "Otra vez"}
    ).status_code == 409

    notices = generated.get("/notifications").json()
    assert notices[0]["tipo"] == "cancelacion" and notices[0]["grupo_id"] == subject["grupo_id"]
    assert "Cita médica" in notices[0]["mensaje"] and subject["nombre"] in notices[0]["mensaje"]
    assert prof.get("/notifications").json()[0]["id"] == notices[0]["id"]

    # A student of that group sees the notice and the cancellation
    generated.patch(f"/users/{student_id(generated)}/group", json={"grupo_id": subject["grupo_id"]})
    student = login(STUDENT["email"], STUDENT["password"])
    assert student.get("/notifications").json()[0]["tipo"] == "cancelacion"
    assert [c["id"] for c in student.get("/cancellations").json()] == [cancellation["id"]]

    assert prof.delete(f"/cancellations/{cancellation['id']}").status_code == 200
    assert generated.get("/notifications").json()[0]["tipo"] == "restablecida"
    assert student.get("/cancellations").json() == []


def student_id(admin: TestClient) -> int:
    return next(u["id"] for u in admin.get("/users").json() if u["email"] == STUDENT["email"])


def test_cancellation_rules(generated):
    teacher, entry, _ = teacher_with_entry(generated)
    prof = login(teacher["email"], TEACHER_PASSWORD)
    day = next_date(entry["dia_semana"])

    wrong_day = prof.post(f"/schedules/{entry['id']}/cancellations", json={"fecha": (day + timedelta(days=1)).isoformat(), "motivo": "x y z"})
    assert wrong_day.status_code == 422 and "no es" in wrong_day.json()["detail"]
    past = prof.post(f"/schedules/{entry['id']}/cancellations", json={"fecha": (day - timedelta(days=7)).isoformat(), "motivo": "x y z"})
    assert past.status_code == 422

    # Another teacher, a student and the read-only user cannot cancel it
    others = [t for t in generated.get("/teachers").json() if t["id"] != teacher["id"]]
    other = login(others[0]["email"], TEACHER_PASSWORD)
    body = {"fecha": day.isoformat(), "motivo": "No es mía"}
    assert other.post(f"/schedules/{entry['id']}/cancellations", json=body).status_code == 403
    assert login(STUDENT["email"], STUDENT["password"]).post(f"/schedules/{entry['id']}/cancellations", json=body).status_code == 403

    # The administrator can
    assert generated.post(f"/schedules/{entry['id']}/cancellations", json=body).status_code == 200


def test_teacher_changes_the_classroom(generated):
    teacher, entry, subject = teacher_with_entry(generated)
    prof = login(teacher["email"], TEACHER_PASSWORD)
    group = next(g for g in generated.get("/groups").json() if g["id"] == subject["grupo_id"])
    schedules = generated.get("/schedules").json()
    busy = {e["aula_id"] for e in schedules if e["dia_semana"] == entry["dia_semana"] and e["hora_inicio"] == entry["hora_inicio"]}
    classrooms = generated.get("/classrooms").json()
    fits = lambda c: c["aforo"] >= group["num_estudiantes"] and subject["tipo_aula"] in ("cualquiera", c["tipo"])
    free = [c for c in classrooms if c["id"] not in busy and fits(c)]
    if not free:
        free = [generated.post("/classrooms", json={"nombre": "Aula nueva", "aforo": 200, "tipo": "laboratorio" if subject["tipo_aula"] == "laboratorio" else "informatica" if subject["tipo_aula"] == "informatica" else "general"}).json()]

    assert prof.patch(f"/schedules/{entry['id']}/classroom", json={"aula_id": entry["aula_id"]}).status_code == 409
    small = generated.post("/classrooms", json={"nombre": "Cubículo", "aforo": 2}).json()
    assert prof.patch(f"/schedules/{entry['id']}/classroom", json={"aula_id": small["id"]}).status_code == 409

    r = prof.patch(f"/schedules/{entry['id']}/classroom", json={"aula_id": free[0]["id"]})
    assert r.status_code == 200 and r.json()["aula_id"] == free[0]["id"]
    notice = generated.get("/notifications").json()[0]
    assert notice["tipo"] == "cambio_aula" and free[0]["nombre"] in notice["mensaje"]

    # Teachers still cannot touch the catalog
    assert prof.post("/classrooms", json={"nombre": "X", "aforo": 10}).status_code == 403


def test_moving_a_block_notifies_the_group(generated):
    entries = generated.get("/schedules").json()
    taken = {(e["dia_semana"], e["hora_inicio"]) for e in entries}
    entry = entries[0]
    for day in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]:
        for hour in range(18, 22):
            start = f"{hour:02d}:00:00"
            if (day, start) not in taken:
                r = generated.put(f"/schedules/{entry['id']}", json={"dia_semana": day, "hora_inicio": start})
                if r.status_code == 200:
                    assert generated.get("/notifications").json()[0]["tipo"] == "cambio_horario"
                    return
    pytest.skip("No free evening slot in the demo data")


def test_teacher_account_follows_the_teacher(client):
    t = client.post("/teachers", json={"nombre": "Nuevo Profe", "email": "nuevo@ucc.edu.co"}).json()
    login("nuevo@ucc.edu.co", TEACHER_PASSWORD)
    client.put(f"/teachers/{t['id']}", json={"nombre": "Nuevo Profe", "email": "otro@ucc.edu.co"})
    login("otro@ucc.edu.co", TEACHER_PASSWORD)
    account = next(u for u in client.get("/users").json() if u["profesor_id"] == t["id"])
    assert client.delete(f"/users/{account['id']}").status_code == 409  # managed from Profesores
    client.delete(f"/teachers/{t['id']}")
    assert all(u["profesor_id"] != t["id"] for u in client.get("/users").json())


def test_admin_creates_students_with_a_group(client, demo_data):
    group = client.get("/groups").json()[0]
    base = {"nombre": "Ana Ruiz", "email": "ana.ruiz@ucc.edu.co", "password": "segura123", "rol": "estudiante"}
    assert client.post("/users", json=base).status_code == 422
    created = client.post("/users", json={**base, "grupo_id": group["id"]})
    assert created.status_code == 200 and created.json()["grupo_id"] == group["id"]
    other = client.get("/groups").json()[1]
    moved = client.patch(f"/users/{created.json()['id']}/group", json={"grupo_id": other["id"]})
    assert moved.json()["grupo_id"] == other["id"]


def test_change_password(client):
    student = login(STUDENT["email"], STUDENT["password"])
    assert student.post("/auth/change-password", json={"actual": "mala", "nueva": "otraClave123"}).status_code == 400
    assert student.post("/auth/change-password", json={"actual": STUDENT["password"], "nueva": "otraClave123"}).status_code == 200
    login(STUDENT["email"], "otraClave123")
