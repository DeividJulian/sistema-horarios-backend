def test_health(client):
    assert client.get("/health").json() == {"estado": "ok", "base_de_datos": "conectada"}


def crear_profesor(client, nombre="Ana Pérez", email="ana@ucc.edu.co"):
    return client.post("/profesores", json={"nombre": nombre, "email": email})


def test_crear_y_listar_profesor(client):
    r = crear_profesor(client)
    assert r.status_code == 200
    assert r.json()["email"] == "ana@ucc.edu.co"
    assert len(client.get("/profesores").json()) == 1


def test_correo_duplicado_da_409(client):
    crear_profesor(client)
    r = crear_profesor(client, nombre="Otra Ana", email="ANA@ucc.edu.co")
    assert r.status_code == 409


def test_correo_invalido_da_422(client):
    r = crear_profesor(client, email="no-es-correo")
    assert r.status_code == 422
    assert "detail" in r.json()


def test_aforo_fuera_de_rango_da_422(client):
    r = client.post("/aulas", json={"nombre": "Aula X", "aforo": 0})
    assert r.status_code == 422


def test_actualizar_y_eliminar_aula(client):
    aula = client.post("/aulas", json={"nombre": "Aula 1", "aforo": 30}).json()
    r = client.put(f"/aulas/{aula['id']}", json={"nombre": "Aula 1B", "aforo": 35})
    assert r.status_code == 200 and r.json()["aforo"] == 35
    assert client.delete(f"/aulas/{aula['id']}").status_code == 200
    assert client.delete(f"/aulas/{aula['id']}").status_code == 404


def test_no_se_elimina_profesor_con_materias(client):
    p = crear_profesor(client).json()
    g = client.post("/grupos", json={"nombre": "7A", "num_estudiantes": 20}).json()
    client.post(
        "/materias",
        json={"nombre": "Bases de Datos", "intensidad_horaria": 3, "grupo_id": g["id"], "profesor_id": p["id"]},
    )
    assert client.delete(f"/profesores/{p['id']}").status_code == 409


def test_disponibilidad_exige_horas_en_punto(client):
    p = crear_profesor(client).json()
    r = client.post(
        "/disponibilidad",
        json={"profesor_id": p["id"], "dia_semana": "Lunes", "hora_inicio": "08:30:00", "hora_fin": "10:00:00"},
    )
    assert r.status_code == 422


def test_disponibilidad_con_rango_invertido_da_422(client):
    p = crear_profesor(client).json()
    r = client.post(
        "/disponibilidad",
        json={"profesor_id": p["id"], "dia_semana": "Lunes", "hora_inicio": "10:00:00", "hora_fin": "08:00:00"},
    )
    assert r.status_code == 422


def test_materia_con_grupo_inexistente_da_404(client):
    p = crear_profesor(client).json()
    r = client.post(
        "/materias",
        json={"nombre": "Redes", "intensidad_horaria": 2, "grupo_id": 999, "profesor_id": p["id"]},
    )
    assert r.status_code == 404
