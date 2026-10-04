from models import Horario


def test_generar_horario_con_datos_demo(client, datos_demo):
    r = client.post("/generar-horario")
    assert r.status_code == 200
    assert r.json()["total_bloques"] == datos_demo["horas_semanales"]
    assert len(client.get("/horarios").json()) == datos_demo["horas_semanales"]


def test_generar_sin_datos_da_409(client):
    r = client.post("/generar-horario")
    assert r.status_code == 409


def test_horario_generado_no_tiene_conflictos(client, datos_demo):
    client.post("/generar-horario")
    r = client.get("/conflictos").json()
    assert r["total"] == 0
    assert r["hay_conflictos"] is False


def test_horarios_por_profesor_y_aula(client, datos_demo):
    client.post("/generar-horario")
    profesor_id = client.get("/profesores").json()[0]["id"]
    aula_id = client.get("/aulas").json()[0]["id"]
    assert client.get(f"/horarios/profesor/{profesor_id}").status_code == 200
    assert client.get(f"/horarios/aula/{aula_id}").status_code == 200
    assert client.get("/horarios/profesor/9999").status_code == 404
    assert client.get("/horarios/aula/9999").status_code == 404


def test_mover_bloque_a_franja_libre(client, datos_demo):
    client.post("/generar-horario")
    bloque = client.get("/horarios").json()[0]
    r = client.put(f"/horarios/{bloque['id']}", json={"dia_semana": "Viernes", "hora_inicio": "20:00:00"})
    assert r.status_code == 200
    assert r.json()["hora_fin"] == "21:00:00"


def test_mover_bloque_nunca_deja_cruces(client, datos_demo):
    client.post("/generar-horario")
    bloques = client.get("/horarios").json()
    for a in bloques[:6]:
        for b in bloques[6:12]:
            r = client.put(f"/horarios/{a['id']}", json={"dia_semana": b["dia_semana"], "hora_inicio": b["hora_inicio"]})
            assert r.status_code in (200, 409)
            # Si el backend aceptó el movimiento, el horario sigue sin cruces de profesor, aula o grupo
            tipos = {c["tipo"] for c in client.get("/conflictos").json()["conflictos"]}
            assert not tipos & {"cruce_profesor", "cruce_aula", "cruce_grupo"}


def test_mover_bloque_con_hora_invalida_da_422(client, datos_demo):
    client.post("/generar-horario")
    bloque = client.get("/horarios").json()[0]
    r = client.put(f"/horarios/{bloque['id']}", json={"dia_semana": "Lunes", "hora_inicio": "03:00:00"})
    assert r.status_code == 422


def test_detecta_cruce_de_profesor(client, datos_demo, db):
    client.post("/generar-horario")
    original = db.query(Horario).first()
    db.add(
        Horario(
            materia_id=original.materia_id,
            aula_id=original.aula_id,
            dia_semana=original.dia_semana,
            hora_inicio=original.hora_inicio,
            hora_fin=original.hora_fin,
        )
    )
    db.commit()
    tipos = {c["tipo"] for c in client.get("/conflictos").json()["conflictos"]}
    assert "cruce_profesor" in tipos
    assert "cruce_aula" in tipos


def test_sin_horario_todas_las_materias_salen_incompletas(client, datos_demo):
    r = client.get("/conflictos").json()
    assert r["total"] == datos_demo["materias"]
    assert {c["tipo"] for c in r["conflictos"]} == {"intensidad_incorrecta"}


def test_eliminar_materia_borra_sus_bloques(client, datos_demo):
    client.post("/generar-horario")
    materia = client.get("/materias").json()[0]
    antes = len(client.get("/horarios").json())
    assert client.delete(f"/materias/{materia['id']}").status_code == 200
    assert len(client.get("/horarios").json()) == antes - materia["intensidad_horaria"]
