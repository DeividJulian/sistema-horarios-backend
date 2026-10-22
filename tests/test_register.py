from fastapi.testclient import TestClient

from main import app
from services.mailer import OUTBOX
from tests.conftest import last_code, login

public = TestClient(app)


def test_register_options_list_the_groups_publicly(client, demo_data):
    groups = public.get("/auth/register-options").json()
    assert len(groups) == demo_data["grupos"]
    assert set(groups[0]) == {"id", "nombre", "jornada"}


def test_a_student_signs_up_with_their_group(client, demo_data):
    group = public.get("/auth/register-options").json()[0]
    body = {"nombre": "Ana Ruiz", "email": "Ana.Ruiz@ucc.edu.co", "grupo_id": group["id"]}
    r = public.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "ana.ruiz@ucc.edu.co"

    r = public.post("/auth/verify", json={"email": "ana.ruiz@ucc.edu.co", "codigo": last_code("ana.ruiz@ucc.edu.co")})
    assert r.status_code == 200, r.text
    user = r.json()["usuario"]
    assert user["rol"] == "estudiante" and user["grupo_id"] == group["id"] and user["verificado"] is True

    # The token works and the account can sign in again with a new code
    me = TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.get("/auth/me").json()["id"] == user["id"]
    login("ana.ruiz@ucc.edu.co")

    assert public.post("/auth/register", json=body).status_code == 409  # same email again


def test_student_sign_up_rules(client, demo_data):
    base = {"nombre": "Luis Díaz", "email": "luis@ucc.edu.co"}
    assert public.post("/auth/register", json=base).status_code == 422  # no group
    assert public.post("/auth/register", json={"email": "luis@ucc.edu.co", "grupo_id": 1}).status_code == 422  # no name
    assert public.post("/auth/register", json={**base, "grupo_id": 9999}).status_code == 404
    assert OUTBOX == []


def test_nobody_signs_up_as_administrator(client, demo_data):
    group = public.get("/auth/register-options").json()[0]
    body = {"nombre": "Intruso", "email": "x@ucc.edu.co", "grupo_id": group["id"], "rol": "admin"}
    public.post("/auth/register", json=body)
    public.post("/auth/verify", json={"email": "x@ucc.edu.co", "codigo": last_code("x@ucc.edu.co")})
    assert login("x@ucc.edu.co").get("/auth/me").json()["rol"] == "estudiante"  # the role in the body is ignored


def test_teachers_do_not_sign_up_they_just_sign_in(client):
    client.post("/teachers", json={"nombre": "Marta Gil", "email": "marta.gil@ucc.edu.co"})
    r = public.post("/auth/register", json={"nombre": "Marta", "email": "marta.gil@ucc.edu.co", "grupo_id": 1})
    assert r.status_code == 409 and "inicia sesión" in r.json()["detail"]

    me = login("marta.gil@ucc.edu.co").get("/auth/me").json()
    assert me["rol"] == "profesor" and me["nombre"] == "Marta Gil"  # the name registered by the administrator


def test_staff_email_cannot_be_used_to_sign_up_as_student(client, demo_data):
    client.post("/users", json={"nombre": "Laura Gómez", "email": "laura@ucc.edu.co", "rol": "usuario"})
    group = public.get("/auth/register-options").json()[0]
    r = public.post("/auth/register", json={"nombre": "Laura", "email": "laura@ucc.edu.co", "grupo_id": group["id"]})
    assert r.status_code == 409
