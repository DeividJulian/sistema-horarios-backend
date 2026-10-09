def test_statistics_full_fulfillment(client, demo_data):
    client.post("/schedules/generate")
    e = client.get("/statistics").json()
    assert e["cumplimiento"]["porcentaje"] == 100.0
    assert e["totales"]["materias"] == demo_data["materias"]
    assert len(e["distribucion_por_dia"]) == 5


def test_statistics_without_schedule(client, demo_data):
    e = client.get("/statistics").json()
    assert e["cumplimiento"]["porcentaje"] == 0.0
    assert e["totales"]["bloques_programados"] == 0


def test_seed_does_not_overwrite_without_reset(client, demo_data):
    assert client.post("/seed").status_code == 409
    assert client.post("/seed?reset=true").status_code == 200
    assert len(client.get("/teachers").json()) == demo_data["profesores"]
