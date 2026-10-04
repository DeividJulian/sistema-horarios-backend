import os

# IMPORTANT: set BEFORE importing the app so the tests never touch Supabase
os.environ["DATABASE_URL"] = "sqlite:///./test_schedule.db"

import pytest
from fastapi.testclient import TestClient

from database import Base, SessionLocal, engine
from main import app

assert str(engine.url).startswith("sqlite"), "Tests must only run against SQLite"


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


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
