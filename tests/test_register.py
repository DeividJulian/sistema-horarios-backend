from fastapi.testclient import TestClient

from main import app
from services.users import TEACHER_PASSWORD

public = TestClient(app)


def login_status(email: str, password: str) -> int:
    return public.post("/auth/login", json={"email": email, "password": password}).status_code


def test_register_options_list_the_groups_publicly(client, demo_data):
    groups = public.get("/auth/register-options").json()
    assert len(groups) == demo_data["grupos"]
    assert set(groups[0]) == {"id", "nombre", "jornada"}


def test_a_student_signs_up_with_their_group(client, demo_data):
    group = public.get("/auth/register-options").json()[0]
    body = {"nombre": "Ana Ruiz", "email": "Ana.Ruiz@ucc.edu.co", "password": "segura123", "rol": "estudiante", "grupo_id": group["id"]}
    r = public.post("/auth/register", json=body)
    assert r.status_code == 200, r.text
    user = r.json()["usuario"]
    assert user["rol"] == "estudiante" and user["grupo_id"] == group["id"] and user["email"] == "ana.ruiz@ucc.edu.co"

    # The token works and only shows the student's group
    me = TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.get("/auth/me").json()["id"] == user["id"]
    assert login_status("ana.ruiz@ucc.edu.co", "segura123") == 200

    assert public.post("/auth/register", json=body).status_code == 409  # same email again


def test_student_sign_up_rules(client, demo_data):
    base = {"nombre": "Luis Díaz", "email": "luis@ucc.edu.co", "password": "segura123", "rol": "estudiante"}
    assert public.post("/auth/register", json=base).status_code == 422  # no group
    assert public.post("/auth/register", json={**base, "grupo_id": 9999}).status_code == 404
    assert public.post("/auth/register", json={**base, "grupo_id": 1, "password": "corta"}).status_code == 422


def test_nobody_signs_up_as_administrator(client):
    body = {"nombre": "Intruso", "email": "x@ucc.edu.co", "password": "segura123", "rol": "admin"}
    assert public.post("/auth/register", json=body).status_code == 422
    assert public.post("/auth/register", json={**body, "rol": "usuario"}).status_code == 422


def test_a_teacher_activates_their_account_once(client):
    client.post("/teachers", json={"nombre": "Marta Gil", "email": "marta.gil@ucc.edu.co"})
    body = {"nombre": "Marta", "email": "marta.gil@ucc.edu.co", "password": "miClave2026", "rol": "profesor"}

    r = public.post("/auth/register", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["usuario"]["rol"] == "profesor"
    assert r.json()["usuario"]["nombre"] == "Marta Gil"  # the name registered by the administrator
    assert login_status("marta.gil@ucc.edu.co", "miClave2026") == 200
    assert login_status("marta.gil@ucc.edu.co", TEACHER_PASSWORD) == 401

    # Nobody else can take over the account afterwards
    again = public.post("/auth/register", json={**body, "password": "otraClave99"})
    assert again.status_code == 409
    assert login_status("marta.gil@ucc.edu.co", "miClave2026") == 200


def test_teacher_sign_up_needs_a_registered_email(client):
    body = {"nombre": "Pedro", "email": "pedro@ucc.edu.co", "password": "segura123", "rol": "profesor"}
    r = public.post("/auth/register", json=body)
    assert r.status_code == 404
    assert "no está registrado como profesor" in r.json()["detail"]
