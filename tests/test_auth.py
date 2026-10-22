from tests.conftest import ADMIN, READER, login


def test_login_with_a_code_returns_token_and_role(anonymous_client):
    session = login(ADMIN["email"])
    me = session.get("/auth/me").json()
    assert me["email"] == ADMIN["email"] and me["rol"] == "admin" and me["verificado"] is True
    assert "password_hash" not in me


def test_login_is_case_insensitive_on_email(anonymous_client):
    assert login(READER["email"].upper()).get("/auth/me").json()["rol"] == "usuario"


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

    created = client.post("/users", json={"nombre": "Laura Gómez", "email": "Laura@ucc.edu.co", "rol": "usuario"})
    assert created.status_code == 200
    assert created.json()["email"] == "laura@ucc.edu.co" and created.json()["verificado"] is False
    assert client.post("/users", json={"nombre": "Laura Gómez", "email": "laura@ucc.edu.co"}).status_code == 409
    assert client.post("/users", json={"nombre": "X", "email": "x@ucc.edu.co"}).status_code == 422

    # No password: the new account enters with a code and is verified from then on
    assert login("laura@ucc.edu.co").get("/auth/me").json()["verificado"] is True

    assert client.delete(f"/users/{created.json()['id']}").status_code == 200


def test_admin_cannot_delete_itself(client):
    me = client.get("/auth/me").json()
    assert client.delete(f"/users/{me['id']}").status_code == 409
