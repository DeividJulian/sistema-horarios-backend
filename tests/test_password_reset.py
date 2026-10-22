from fastapi.testclient import TestClient

from main import app
from services.users import TEACHER_PASSWORD
from tests.conftest import ADMIN, READER


def login_status(email: str, password: str) -> int:
    return TestClient(app).post("/auth/login", json={"email": email, "password": password}).status_code


def user_id(client, email: str) -> int:
    return next(u["id"] for u in client.get("/users").json() if u["email"] == email)


def test_teacher_who_forgot_the_password_gets_the_initial_one_back(client, anonymous_client):
    client.post("/teachers", json={"nombre": "Marcela Torres", "email": "marcela@ucc.edu.co"})
    # The teacher activates the account with a password of their own... and forgets it
    r = anonymous_client.post("/auth/register", json={"email": "marcela@ucc.edu.co", "password": "olvidada123", "rol": "profesor"})
    assert r.status_code == 200
    assert login_status("marcela@ucc.edu.co", TEACHER_PASSWORD) == 401

    r = client.post(f"/users/{user_id(client, 'marcela@ucc.edu.co')}/reset-password")
    assert r.status_code == 200
    assert r.json()["password"] == TEACHER_PASSWORD
    assert login_status("marcela@ucc.edu.co", TEACHER_PASSWORD) == 200
    assert login_status("marcela@ucc.edu.co", "olvidada123") == 401

    # With the initial password back, the teacher can activate the account again with a new one
    r = anonymous_client.post("/auth/register", json={"email": "marcela@ucc.edu.co", "password": "nuevaClave1", "rol": "profesor"})
    assert r.status_code == 200
    assert login_status("marcela@ucc.edu.co", "nuevaClave1") == 200


def test_other_roles_go_back_to_their_initial_password(client):
    reader = TestClient(app).post("/auth/login", json={"email": READER["email"], "password": READER["password"]}).json()
    headers = {"Authorization": f"Bearer {reader['access_token']}"}
    TestClient(app).post("/auth/change-password", json={"actual": READER["password"], "nueva": "otraClave99"}, headers=headers)
    assert login_status(READER["email"], READER["password"]) == 401

    r = client.post(f"/users/{user_id(client, READER['email'])}/reset-password")
    assert r.status_code == 200 and r.json()["password"] == READER["password"]
    assert login_status(READER["email"], READER["password"]) == 200


def test_only_administrators_reset_and_not_their_own(client, reader_client):
    admin_id = user_id(client, ADMIN["email"])
    assert client.post(f"/users/{admin_id}/reset-password").status_code == 409
    assert client.post("/users/99999/reset-password").status_code == 404
    assert reader_client.post(f"/users/{admin_id}/reset-password").status_code == 403
