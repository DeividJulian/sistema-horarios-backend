from tests.conftest import ADMIN, READER


def test_login_returns_token_and_role(anonymous_client):
    r = anonymous_client.post("/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["usuario"]["rol"] == "admin"
    assert "password_hash" not in body["usuario"]

    me = anonymous_client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == ADMIN["email"]


def test_login_is_case_insensitive_on_email(anonymous_client):
    r = anonymous_client.post("/auth/login", json={"email": READER["email"].upper(), "password": READER["password"]})
    assert r.status_code == 200 and r.json()["usuario"]["rol"] == "usuario"


def test_wrong_password_is_rejected(anonymous_client):
    r = anonymous_client.post("/auth/login", json={"email": ADMIN["email"], "password": "incorrecta"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Correo o contraseña incorrectos."


def test_data_requires_login(anonymous_client):
    assert anonymous_client.get("/teachers").status_code == 401
    assert anonymous_client.post("/schedules/generate").status_code == 401
    assert anonymous_client.get("/health").status_code == 200  # health stays public for the hosting checks


def test_invalid_token_is_rejected(anonymous_client):
    r = anonymous_client.get("/teachers", headers={"Authorization": "Bearer no-es-un-token"})
    assert r.status_code == 401


def test_reader_can_read_but_not_change(reader_client):
    assert reader_client.get("/teachers").status_code == 200
    assert reader_client.get("/schedules").status_code == 200
    assert reader_client.get("/statistics").status_code == 200

    r = reader_client.post("/teachers", json={"nombre": "Ana", "email": "ana@ucc.edu.co"})
    assert r.status_code == 403
    assert "solo lectura" in r.json()["detail"]
    assert reader_client.post("/schedules/generate").status_code == 403
    assert reader_client.post("/seed").status_code == 403
    assert reader_client.get("/users").status_code == 403


def test_admin_manages_users(client):
    users = client.get("/users").json()
    assert {u["rol"] for u in users} == {"admin", "usuario", "estudiante"}

    created = client.post(
        "/users", json={"nombre": "Laura Gómez", "email": "laura@ucc.edu.co", "password": "segura123", "rol": "usuario"}
    )
    assert created.status_code == 200
    assert client.post(
        "/users", json={"nombre": "Laura Gómez", "email": "laura@ucc.edu.co", "password": "segura123"}
    ).status_code == 409
    assert client.post("/users", json={"nombre": "X Y", "email": "x@ucc.edu.co", "password": "corta"}).status_code == 422

    login = client.post("/auth/login", json={"email": "laura@ucc.edu.co", "password": "segura123"})
    assert login.status_code == 200

    assert client.delete(f"/users/{created.json()['id']}").status_code == 200


def test_admin_cannot_delete_itself(client):
    me = client.get("/auth/me").json()
    assert client.delete(f"/users/{me['id']}").status_code == 409
