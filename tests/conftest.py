import os

# IMPORTANTE: se fija ANTES de importar la app para que los tests nunca toquen Supabase
os.environ["DATABASE_URL"] = "sqlite:///./test_horarios.db"

import pytest
from fastapi.testclient import TestClient

from database import Base, SessionLocal, engine
from main import app

assert str(engine.url).startswith("sqlite"), "Los tests solo deben correr contra SQLite"


@pytest.fixture(autouse=True)
def base_limpia():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture
def datos_demo(client):
    """Carga los datos de demostración y devuelve el resumen."""
    r = client.post("/seed")
    assert r.status_code == 200
    return r.json()["resumen"]
