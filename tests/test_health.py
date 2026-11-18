from sqlalchemy.exc import OperationalError

from database import get_db
from main import app


class BrokenSession:
    """Simulates a database that does not answer."""

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def broken_db():
    yield BrokenSession()


def test_health_checks_the_database_without_a_session(anonymous_client):
    r = anonymous_client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_returns_503_when_the_database_fails(anonymous_client):
    app.dependency_overrides[get_db] = broken_db
    try:
        r = anonymous_client.get("/health")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 503 and r.json() == {"status": "error"}
    assert "connection refused" not in r.text  # no internal details leak
