from models import ScheduleEntry


def test_generate_schedule_with_demo_data(client, demo_data):
    r = client.post("/schedules/generate")
    assert r.status_code == 200
    assert r.json()["total_bloques"] == demo_data["horas_semanales"]
    assert len(client.get("/schedules").json()) == demo_data["horas_semanales"]


def test_generate_without_data_returns_409(client):
    r = client.post("/schedules/generate")
    assert r.status_code == 409


def test_generated_schedule_has_no_conflicts(client, demo_data):
    client.post("/schedules/generate")
    r = client.get("/conflicts").json()
    assert r["total"] == 0
    assert r["hay_conflictos"] is False


def test_schedule_by_teacher_and_classroom(client, demo_data):
    client.post("/schedules/generate")
    profesor_id = client.get("/teachers").json()[0]["id"]
    aula_id = client.get("/classrooms").json()[0]["id"]
    assert client.get(f"/schedules/teacher/{profesor_id}").status_code == 200
    assert client.get(f"/schedules/classroom/{aula_id}").status_code == 200
    assert client.get("/schedules/teacher/9999").status_code == 404
    assert client.get("/schedules/classroom/9999").status_code == 404


def test_move_block_to_free_slot(client, demo_data):
    client.post("/schedules/generate")
    block = client.get("/schedules").json()[0]
    r = client.put(f"/schedules/{block['id']}", json={"dia_semana": "Viernes", "hora_inicio": "20:00:00"})
    assert r.status_code == 200
    assert r.json()["hora_fin"] == "21:00:00"


def test_moving_blocks_never_leaves_clashes(client, demo_data):
    client.post("/schedules/generate")
    blocks = client.get("/schedules").json()
    for a in blocks[:6]:
        for b in blocks[6:12]:
            r = client.put(f"/schedules/{a['id']}", json={"dia_semana": b["dia_semana"], "hora_inicio": b["hora_inicio"]})
            assert r.status_code in (200, 409)
            # If the backend accepted the move, the schedule still has no teacher, classroom or group clashes
            kinds = {c["tipo"] for c in client.get("/conflicts").json()["conflictos"]}
            assert not kinds & {"cruce_profesor", "cruce_aula", "cruce_grupo"}


def test_move_block_with_invalid_hour_returns_422(client, demo_data):
    client.post("/schedules/generate")
    block = client.get("/schedules").json()[0]
    r = client.put(f"/schedules/{block['id']}", json={"dia_semana": "Lunes", "hora_inicio": "03:00:00"})
    assert r.status_code == 422


def test_detects_teacher_clash(client, demo_data, db):
    client.post("/schedules/generate")
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
    kinds = {c["tipo"] for c in client.get("/conflicts").json()["conflictos"]}
    assert "cruce_profesor" in kinds
    assert "cruce_aula" in kinds


def test_without_schedule_every_subject_is_incomplete(client, demo_data):
    r = client.get("/conflicts").json()
    assert r["total"] == demo_data["materias"]
    assert {c["tipo"] for c in r["conflictos"]} == {"intensidad_incorrecta"}


def test_deleting_subject_removes_its_blocks(client, demo_data):
    client.post("/schedules/generate")
    subject = client.get("/subjects").json()[0]
    before = len(client.get("/schedules").json())
    assert client.delete(f"/subjects/{subject['id']}").status_code == 200
    assert len(client.get("/schedules").json()) == before - subject["intensidad_horaria"]
