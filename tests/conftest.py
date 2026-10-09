import os

# IMPORTANT: set BEFORE importing the app so the tests never touch Supabase
os.environ["DATABASE_URL"] = "sqlite:///./test_schedule.db"

import pytest
from fastapi.testclient import TestClient

from database import Base, SessionLocal, engine
from main import app
from models import User
from security import create_token
from services.users import DEFAULT_USERS, ensure_default_users

ADMIN, READER, STUDENT = DEFAULT_USERS

assert str(engine.url).startswith("sqlite"), "Tests must only run against SQLite"


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _client_as(email: str | None) -> TestClient:
    """Test client signed in as the given default account (None = anonymous)."""
    with SessionLocal() as session:
        ensure_default_users(session)
        user = session.query(User).filter(User.email == email).first() if email else None
        headers = {"Authorization": f"Bearer {create_token(user)}"} if user else {}
    return TestClient(app, headers=headers)


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
