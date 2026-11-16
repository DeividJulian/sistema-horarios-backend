"""Demo accounts: administrador@gmail.com and profesor@gmail.com enter with the demo password, never with a code."""
import pytest
from fastapi.testclient import TestClient

import config
from database import SessionLocal
from main import app
from models import Teacher, User
from services.mailer import OUTBOX
from services.users import ensure_demo_accounts


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(config, "DEMO_ACCOUNTS", True)
    monkeypatch.setattr(config, "DEMO_PASSWORD", "demo123")
    with SessionLocal() as session:
        ensure_demo_accounts(session)
    return TestClient(app)


def _password_login(client: TestClient, email: str, password: str = "demo123"):
    return client.post("/auth/password-login", json={"email": email, "password": password})


def test_demo_admin_enters_with_the_password(demo):
    r = _password_login(demo, "Administrador@gmail.com")
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["rol"] == "admin"
    me = demo.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["email"] == "administrador@gmail.com"


def test_wrong_password_or_other_accounts_are_refused(demo):
    assert _password_login(demo, "administrador@gmail.com", "otra").status_code == 401
    # Any other account keeps the emailed code: the password does not open it
    with SessionLocal() as session:
        session.add(User(nombre="Ana", email="ana@test.com", rol="admin", verificado=True))
        session.commit()
    assert _password_login(demo, "ana@test.com").status_code == 401


def test_no_code_is_ever_emailed_to_a_demo_inbox(demo):
    r = demo.post("/auth/login", json={"email": "profesor@gmail.com"})
    assert r.status_code == 400 and "contraseña" in r.json()["detail"]
    assert demo.post("/auth/register", json={"nombre": "Xavier Pérez", "email": "administrador@gmail.com", "grupo_id": 1}).status_code == 409
    assert OUTBOX == []


def test_the_demo_teacher_has_classes_after_loading_the_demo_data(demo):
    admin = _password_login(demo, "administrador@gmail.com").json()["access_token"]
    headers = {"Authorization": f"Bearer {admin}"}
    assert demo.post("/seed?dataset=demo", headers=headers).status_code == 200
    assert demo.post("/schedules/generate", headers=headers).status_code == 200

    r = _password_login(demo, "profesor@gmail.com")
    assert r.status_code == 200, r.text
    teacher = r.json()["usuario"]
    assert teacher["rol"] == "profesor" and teacher["profesor_id"] is not None
    mine = demo.get("/schedules", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()
    assert len(mine) > 0


def test_existing_data_gets_a_demo_teacher_and_an_empty_database_does_not(monkeypatch):
    monkeypatch.setattr(config, "DEMO_ACCOUNTS", True)
    with SessionLocal() as session:
        ensure_demo_accounts(session)
        assert session.query(Teacher).count() == 0  # the first data load is not blocked
        session.add(Teacher(nombre="Otra", email="otra@ucc.edu.co"))
        session.commit()
        ensure_demo_accounts(session)
        assert session.query(Teacher).filter(Teacher.email == "profesor@gmail.com").count() == 1


def test_demo_accounts_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(config, "DEMO_ACCOUNTS", False)
    client = TestClient(app)
    assert _password_login(client, "administrador@gmail.com").status_code == 401
