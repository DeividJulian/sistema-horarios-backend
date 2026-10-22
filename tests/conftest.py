import os

# IMPORTANT: set BEFORE importing the app so the tests never touch Supabase
os.environ["DATABASE_URL"] = "sqlite:///./test_schedule.db"
os.environ["SECRET_KEY"] = "test-secret-for-pytest-only-0123456789abcdef"
# Emails stay in memory (services.mailer.OUTBOX); no wait between codes unless a test asks for it
os.environ["EMAIL_BACKEND"] = "memoria"
os.environ["CODIGO_ESPERA_SEGUNDOS"] = "0"
# Blank values win over a developer's .env (load_dotenv doesn't override): no real admin, no real AI provider
for _name in ("ADMIN_EMAIL", "AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL"):
    os.environ[_name] = ""

import re

import pytest
from fastapi.testclient import TestClient

from database import Base, SessionLocal, engine
from main import app
from models import User
from security import create_token
from services.mailer import OUTBOX

# Accounts every test can use (already verified)
ADMIN = {"nombre": "Administrador", "email": "admin@test.com", "rol": "admin"}
READER = {"nombre": "Usuario de consulta", "email": "consulta@test.com", "rol": "usuario"}
STUDENT = {"nombre": "Estudiante de prueba", "email": "estudiante@test.com", "rol": "estudiante"}

assert str(engine.url).startswith("sqlite"), "Tests must only run against SQLite"


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    OUTBOX.clear()
    yield


def _ensure_test_users(session) -> None:
    for account in (ADMIN, READER, STUDENT):
        if not session.query(User).filter(User.email == account["email"]).first():
            session.add(User(**account, verificado=True))
    session.commit()


def _client_as(email: str | None) -> TestClient:
    """Test client signed in as the given test account (None = anonymous)."""
    with SessionLocal() as session:
        _ensure_test_users(session)
        user = session.query(User).filter(User.email == email).first() if email else None
        headers = {"Authorization": f"Bearer {create_token(user)}"} if user else {}
    return TestClient(app, headers=headers)


def last_code(email: str) -> str:
    """The six digits of the last email sent to that address."""
    mail = next(m for m in reversed(OUTBOX) if m["to"] == email.lower())
    return re.search(r"\b(\d{6})\b", mail["text"]).group(1)


def login(email: str) -> TestClient:
    """Asks for a code, reads it from the in-memory outbox and enters with it."""
    public = TestClient(app)
    r = public.post("/auth/login", json={"email": email})
    assert r.status_code == 200, r.text
    r = public.post("/auth/verify", json={"email": email, "codigo": last_code(email)})
    assert r.status_code == 200, r.text
    return TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})


def place_student(admin: TestClient, group_id: int | None = None) -> int:
    """Puts the test student in a group (the first one by default) and returns the student's account id."""
    student_id = next(u["id"] for u in admin.get("/users").json() if u["email"] == STUDENT["email"])
    group_id = group_id or admin.get("/groups").json()[0]["id"]
    assert admin.patch(f"/users/{student_id}/group", json={"grupo_id": group_id}).status_code == 200
    return student_id


@pytest.fixture
def client():
    """Signed in as administrator, so the data tests can create and change everything."""
    return _client_as(ADMIN["email"])


@pytest.fixture
def reader_client():
    """Signed in with the read-only role."""
    return _client_as(READER["email"])


@pytest.fixture
def anonymous_client():
    return _client_as(None)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def demo_data(client):
    """Loads the demo data and returns the summary."""
    r = client.post("/seed")
    assert r.status_code == 200
    return r.json()["resumen"]
