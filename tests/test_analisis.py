def test_estadisticas_cumplimiento_total(client, datos_demo):
    client.post("/generar-horario")
    e = client.get("/estadisticas").json()
    assert e["cumplimiento"]["porcentaje"] == 100.0
    assert e["totales"]["materias"] == datos_demo["materias"]
    assert len(e["distribucion_por_dia"]) == 5


def test_estadisticas_sin_horario(client, datos_demo):
    e = client.get("/estadisticas").json()
    assert e["cumplimiento"]["porcentaje"] == 0.0
    assert e["totales"]["bloques_programados"] == 0


def test_seed_no_sobrescribe_sin_reiniciar(client, datos_demo):
    assert client.post("/seed").status_code == 409
    assert client.post("/seed?reiniciar=true").status_code == 200
    assert len(client.get("/profesores").json()) == datos_demo["profesores"]
