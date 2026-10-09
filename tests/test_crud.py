def test_health(client):
    assert client.get("/health").json() == {"estado": "ok", "base_de_datos": "conectada"}


def create_teacher(client, name="Ana Pérez", email="ana@ucc.edu.co"):
    return client.post("/teachers", json={"nombre": name, "email": email})


def test_create_and_list_teacher(client):
    r = create_teacher(client)
    assert r.status_code == 200
    assert r.json()["email"] == "ana@ucc.edu.co"
    assert len(client.get("/teachers").json()) == 1


def test_duplicate_email_returns_409(client):
    create_teacher(client)
    r = create_teacher(client, name="Otra Ana", email="ANA@ucc.edu.co")
    assert r.status_code == 409


def test_invalid_email_returns_422(client):
    r = create_teacher(client, email="no-es-correo")
    assert r.status_code == 422
    assert "detail" in r.json()


def test_capacity_out_of_range_returns_422(client):
    r = client.post("/classrooms", json={"nombre": "Aula X", "aforo": 0})
    assert r.status_code == 422


def test_update_and_delete_classroom(client):
    classroom = client.post("/classrooms", json={"nombre": "Aula 1", "aforo": 30}).json()
    r = client.put(f"/classrooms/{classroom['id']}", json={"nombre": "Aula 1B", "aforo": 35})
    assert r.status_code == 200 and r.json()["aforo"] == 35
    assert client.delete(f"/classrooms/{classroom['id']}").status_code == 200
    assert client.delete(f"/classrooms/{classroom['id']}").status_code == 404


def test_cannot_delete_teacher_with_subjects(client):
    p = create_teacher(client).json()
    g = client.post("/groups", json={"nombre": "7A", "num_estudiantes": 20}).json()
    client.post(
        "/subjects",
        json={"nombre": "Bases de Datos", "intensidad_horaria": 3, "grupo_id": g["id"], "profesor_id": p["id"]},
    )
    assert client.delete(f"/teachers/{p['id']}").status_code == 409


def test_availability_requires_on_the_hour_times(client):
    p = create_teacher(client).json()
    r = client.post(
        "/availability",
        json={"profesor_id": p["id"], "dia_semana": "Lunes", "hora_inicio": "08:30:00", "hora_fin": "10:00:00"},
    )
    assert r.status_code == 422


def test_availability_with_inverted_range_returns_422(client):
    p = create_teacher(client).json()
    r = client.post(
        "/availability",
        json={"profesor_id": p["id"], "dia_semana": "Lunes", "hora_inicio": "10:00:00", "hora_fin": "08:00:00"},
    )
    assert r.status_code == 422


def test_subject_with_missing_group_returns_404(client):
    p = create_teacher(client).json()
    r = client.post(
        "/subjects",
        json={"nombre": "Redes", "intensidad_horaria": 2, "grupo_id": 999, "profesor_id": p["id"]},
    )
    assert r.status_code == 404
