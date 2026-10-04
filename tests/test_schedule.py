from models import ScheduleEntry


def test_generate_schedule_with_demo_data(client, demo_data):
    r = client.post("/generar-horario")
    assert r.status_code == 200
    assert r.json()["total_bloques"] == demo_data["horas_semanales"]
    assert len(client.get("/horarios").json()) == demo_data["horas_semanales"]


def test_generate_without_data_returns_409(client):
    r = client.post("/generar-horario")
    assert r.status_code == 409


def test_generated_schedule_has_no_conflicts(client, demo_data):
    client.post("/generar-horario")
    r = client.get("/conflictos").json()
    assert r["total"] == 0
    assert r["hay_conflictos"] is False


def test_schedule_by_teacher_and_classroom(client, demo_data):
    client.post("/generar-horario")
    profesor_id = client.get("/profesores").json()[0]["id"]
    aula_id = client.get("/aulas").json()[0]["id"]
    assert client.get(f"/horarios/profesor/{profesor_id}").status_code == 200
    assert client.get(f"/horarios/aula/{aula_id}").status_code == 200
    assert client.get("/horarios/profesor/9999").status_code == 404
    assert client.get("/horarios/aula/9999").status_code == 404


def test_move_block_to_free_slot(client, demo_data):
    client.post("/generar-horario")
    block = client.get("/horarios").json()[0]
    r = client.put(f"/horarios/{block['id']}", json={"dia_semana": "Viernes", "hora_inicio": "20:00:00"})
    assert r.status_code == 200
    assert r.json()["hora_fin"] == "21:00:00"


def test_moving_blocks_never_leaves_clashes(client, demo_data):
    client.post("/generar-horario")
    blocks = client.get("/horarios").json()
    for a in blocks[:6]:
        for b in blocks[6:12]:
            r = client.put(f"/horarios/{a['id']}", json={"dia_semana": b["dia_semana"], "hora_inicio": b["hora_inicio"]})
            assert r.status_code in (200, 409)
            # If the backend accepted the move, the schedule still has no teacher, classroom or group clashes
            kinds = {c["tipo"] for c in client.get("/conflictos").json()["conflictos"]}
            assert not kinds & {"cruce_profesor", "cruce_aula", "cruce_grupo"}


def test_move_block_with_invalid_hour_returns_422(client, demo_data):
    client.post("/generar-horario")
    block = client.get("/horarios").json()[0]
    r = client.put(f"/horarios/{block['id']}", json={"dia_semana": "Lunes", "hora_inicio": "03:00:00"})
    assert r.status_code == 422


def test_detects_teacher_clash(client, demo_data, db):
    client.post("/generar-horario")
    original = db.query(ScheduleEntry).first()
    db.add(
        ScheduleEntry(
            materia_id=original.materia_id,
            aula_id=original.aula_id,
            dia_semana=original.dia_semana,
            hora_inicio=original.hora_inicio,
            hora_fin=original.hora_fin,
        )
    )
    db.commit()
    kinds = {c["tipo"] for c in client.get("/conflictos").json()["conflictos"]}
    assert "cruce_profesor" in kinds
    assert "cruce_aula" in kinds


def test_without_schedule_every_subject_is_incomplete(client, demo_data):
    r = client.get("/conflictos").json()
    assert r["total"] == demo_data["materias"]
    assert {c["tipo"] for c in r["conflictos"]} == {"intensidad_incorrecta"}


def test_deleting_subject_removes_its_blocks(client, demo_data):
    client.post("/generar-horario")
    subject = client.get("/materias").json()[0]
    before = len(client.get("/horarios").json())
    assert client.delete(f"/materias/{subject['id']}").status_code == 200
    assert len(client.get("/horarios").json()) == before - subject["intensidad_horaria"]
