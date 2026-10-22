"""AI layer with the provider's HTTP simulated: no test ever calls Groq."""
import io
import json
import socket
import urllib.error

import pytest

from services import ai, llm
from tests.conftest import login, place_student, STUDENT

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class FakeResponse:
    def __init__(self, body: dict, status: int = 200):
        self.status = status
        self.headers = {"Content-Type": "application/json"}
        self._data = json.dumps(body).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def answer(content: dict) -> FakeResponse:
    return FakeResponse({"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}, "finish_reason": "stop"}]})


def http_error(code: int, headers: dict | None = None):
    return urllib.error.HTTPError(GROQ_URL, code, "error", headers or {}, io.BytesIO(b'{"error":{"message":"x"}}'))


@pytest.fixture
def groq(monkeypatch):
    """AI configured with Groq; every request is recorded and answered by the queued responses."""
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("AI_API_KEY", "gsk_clave_de_prueba")
    monkeypatch.setattr(llm, "RETRY_DELAY_SECONDS", 0)
    state = {"requests": [], "responses": []}

    def fake_urlopen(request, timeout):
        state["requests"].append(
            {"url": request.full_url, "headers": dict(request.header_items()), "body": json.loads(request.data), "timeout": timeout}
        )
        result = state["responses"].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    return state


@pytest.fixture
def generated(client, demo_data):
    assert client.post("/schedules/generate").status_code == 200
    return client


def conflicting_entry(admin) -> dict:
    """Moves a block to a slot outside its teacher's availability, so it shows a conflict."""
    from database import SessionLocal
    from models import TeacherAvailability

    with SessionLocal() as db:
        availability = [(a.profesor_id, a.dia_semana, a.hora_inicio.hour, a.hora_fin.hour) for a in db.query(TeacherAvailability)]
    entries = admin.get("/schedules").json()
    subjects = {s["id"]: s for s in admin.get("/subjects").json()}
    groups = {g["id"]: g for g in admin.get("/groups").json()}
    for entry in entries:
        subject = subjects[entry["materia_id"]]
        free = {(day, h) for teacher, day, start, end in availability if teacher == subject["profesor_id"] for h in range(start, end)}
        start, end = {"manana": (6, 13), "tarde": (12, 19), "noche": (17, 22)}.get(groups[subject["grupo_id"]]["jornada"], (6, 22))
        for day in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]:
            for h in range(start, end):
                if (day, h) not in free:
                    r = admin.put(f"/schedules/{entry['id']}", json={"dia_semana": day, "hora_inicio": f"{h:02d}:00:00"})
                    if r.status_code == 200:
                        return r.json()
    pytest.skip("No slot outside availability in the demo data")


def test_status_without_key(client, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    status = client.get("/ai/status").json()
    assert status == {"configurada": False, "proveedor": "groq", "nombre_proveedor": "Groq", "modelo": "openai/gpt-oss-20b"}


def test_students_do_not_use_the_ai(generated):
    place_student(generated)
    student = login(STUDENT["email"])
    assert student.get("/ai/status").status_code == 403
    entry = generated.get("/schedules").json()[0]
    assert student.post("/ai/notices/draft", json={"horario_id": entry["id"], "tipo": "cancelacion"}).status_code == 403


def test_without_key_the_ai_answers_503(generated, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    entry = generated.get("/schedules").json()[0]
    r = generated.post(f"/ai/conflicts/{entry['id']}/suggestion")
    assert r.status_code == 503 and "AI_API_KEY" in r.json()["detail"]
    r = generated.post("/ai/notices/draft", json={"horario_id": entry["id"], "tipo": "cancelacion", "motivo": "Congreso"})
    assert r.status_code == 503


def test_conflict_suggestion_calls_groq_with_valid_options_and_no_personal_data(generated, groq):
    entry = conflicting_entry(generated)
    groq["responses"].append(answer({"recomendada": 0, "explicacion": "Docente A no está disponible a esa hora; la opción 0 lo resuelve.", "motivos": ["Sin horas muertas", "Mismo día"]}))

    r = generated.post(f"/ai/conflicts/{entry['id']}/suggestion")
    assert r.status_code == 200, r.text
    body = r.json()
    sent = groq["requests"][0]

    # Groq's OpenAI-compatible endpoint, with the key in the header and a strict JSON schema
    assert sent["url"] == GROQ_URL
    assert sent["headers"]["Authorization"] == "Bearer gsk_clave_de_prueba"
    assert sent["body"]["model"] == "openai/gpt-oss-20b"
    assert sent["body"]["response_format"]["type"] == "json_schema"
    assert sent["body"]["response_format"]["json_schema"]["strict"] is True

    # Never a teacher's name or email in what goes to the model
    prompt = json.dumps(sent["body"], ensure_ascii=False)
    for teacher in generated.get("/teachers").json():
        assert teacher["email"] not in prompt
        for part in teacher["nombre"].split():
            if len(part) >= 3:
                assert part not in prompt, part
    assert "Docente A" in prompt

    # The answer shows the real name again, and the recommended option really fixes the conflict
    subject = next(s for s in generated.get("/subjects").json() if s["id"] == entry["materia_id"])
    teacher = next(t for t in generated.get("/teachers").json() if t["id"] == subject["profesor_id"])
    assert body["conflictos"] and body["opciones"] and body["recomendada"] == 0
    assert body["proveedor"] == "Groq" and body["modelo"] == "openai/gpt-oss-20b"
    assert "Docente" not in body["explicacion"] or teacher["nombre"] in body["explicacion"]
    option = body["opciones"][0]
    moved = generated.put(f"/schedules/{entry['id']}", json={"dia_semana": option["dia_semana"], "hora_inicio": option["hora_inicio"], "aula_id": option["aula_id"]})
    assert moved.status_code == 200 and moved.json()["aula_id"] == option["aula_id"]
    assert all(entry["id"] not in c["horario_ids"] for c in generated.get("/conflicts").json()["conflictos"])


def test_every_option_respects_the_rules(generated):
    entry_id = conflicting_entry(generated)["id"]
    from database import SessionLocal
    from models import ScheduleEntry

    with SessionLocal() as db:
        entry = db.get(ScheduleEntry, entry_id)
        options = ai.alternatives(db, entry)
        assert options
        for option in options:
            others = [e for e in db.query(ScheduleEntry).all() if e.id != entry_id and e.dia_semana == option["dia_semana"] and e.hora_inicio.hour == option["hora"]]
            assert all(e.aula_id != option["aula_id"] for e in others)
            assert all(e.subject.profesor_id != entry.subject.profesor_id for e in others)
            assert all(e.subject.grupo_id != entry.subject.grupo_id for e in others)


def test_only_administrators_ask_for_conflict_suggestions(generated, reader_client):
    entry = generated.get("/schedules").json()[0]
    assert reader_client.post(f"/ai/conflicts/{entry['id']}/suggestion").status_code == 403
    assert generated.post("/ai/conflicts/999999/suggestion").status_code == 404


def test_rate_limit_is_429_with_retry_after(generated, groq):
    entry = generated.get("/schedules").json()[0]
    groq["responses"].append(http_error(429, {"Retry-After": "20"}))
    r = generated.post(f"/ai/conflicts/{entry['id']}/suggestion")
    assert r.status_code == 429 and r.headers["Retry-After"] == "20" and "límite de uso de Groq" in r.json()["detail"]
    assert len(groq["requests"]) == 1  # usage limits are not retried


def test_provider_down_is_retried_once_then_502(generated, groq):
    entry = generated.get("/schedules").json()[0]
    groq["responses"] += [http_error(503), http_error(503)]
    r = generated.post(f"/ai/conflicts/{entry['id']}/suggestion")
    assert r.status_code == 502 and "no está disponible" in r.json()["detail"]
    assert len(groq["requests"]) == 2


@pytest.mark.parametrize("failure", [socket.timeout("lento"), urllib.error.URLError("sin red")])
def test_slow_or_unreachable_provider_is_502(generated, groq, failure):
    entry = generated.get("/schedules").json()[0]
    groq["responses"].append(failure)
    assert generated.post(f"/ai/conflicts/{entry['id']}/suggestion").status_code == 502


def test_invalid_answers_are_502_never_500(generated, groq):
    entry = generated.get("/schedules").json()[0]
    groq["responses"] += [
        FakeResponse({"choices": [{"message": {"content": "esto no es JSON"}}]}),
        FakeResponse({"choices": [{"message": {"content": None, "refusal": "No puedo"}}]}),
        http_error(401),
    ]
    for _ in range(3):
        r = generated.post(f"/ai/conflicts/{entry['id']}/suggestion")
        assert r.status_code == 502
    assert "AI_API_KEY" in r.json()["detail"]


def test_a_recommendation_out_of_range_is_ignored(generated, groq):
    entry = conflicting_entry(generated)
    groq["responses"].append(answer({"recomendada": 99, "explicacion": "Opción inventada", "motivos": []}))
    assert generated.post(f"/ai/conflicts/{entry['id']}/suggestion").json()["recomendada"] is None


def test_teacher_drafts_a_notice_without_sending_personal_data(generated, groq):
    entry = generated.get("/schedules").json()[0]
    subject = next(s for s in generated.get("/subjects").json() if s["id"] == entry["materia_id"])
    teacher = next(t for t in generated.get("/teachers").json() if t["id"] == subject["profesor_id"])
    prof = login(teacher["email"])
    groq["responses"].append(answer({"titulo": "Clase cancelada", "mensaje": f"La clase de {subject['nombre']} no se dictará por un congreso. Disculpen las molestias."}))

    reason = f"Congreso; escribanme a {teacher['email']} o al 300 123 4567. Atte. {teacher['nombre']}"
    r = prof.post("/ai/notices/draft", json={"horario_id": entry["id"], "tipo": "cancelacion", "fecha": "2026-11-02", "motivo": reason})
    assert r.status_code == 200, r.text
    assert r.json()["titulo"] == "Clase cancelada" and subject["nombre"] in r.json()["mensaje"]

    prompt = json.dumps(groq["requests"][0]["body"], ensure_ascii=False)
    assert teacher["email"] not in prompt and "300 123 4567" not in prompt
    assert all(part not in prompt for part in teacher["nombre"].split() if len(part) >= 3)
    assert "[correo]" in prompt and "[teléfono]" in prompt and subject["nombre"] in prompt


def test_only_the_teacher_of_the_class_drafts_its_notice(generated):
    entry = generated.get("/schedules").json()[0]
    subject = next(s for s in generated.get("/subjects").json() if s["id"] == entry["materia_id"])
    other = next(t for t in generated.get("/teachers").json() if t["id"] != subject["profesor_id"])
    r = login(other["email"]).post("/ai/notices/draft", json={"horario_id": entry["id"], "tipo": "cancelacion"})
    assert r.status_code == 403


def test_classroom_notice_needs_the_new_classroom(generated, groq):
    entry = generated.get("/schedules").json()[0]
    r = generated.post("/ai/notices/draft", json={"horario_id": entry["id"], "tipo": "cambio_aula"})
    assert r.status_code == 422
    assert groq["requests"] == []


def test_the_reviewed_notice_is_what_the_students_receive(generated):
    from services.class_changes import today

    entry = generated.get("/schedules").json()[0]
    day = today()
    from services.class_changes import WEEKDAY_INDEX
    from datetime import timedelta

    while day.weekday() != WEEKDAY_INDEX[entry["dia_semana"]]:
        day += timedelta(days=1)
    text = "Queridos estudiantes: la clase de hoy no se dictará por un congreso. Nos vemos la próxima semana."
    r = generated.post(f"/schedules/{entry['id']}/cancellations", json={"fecha": day.isoformat(), "motivo": "Congreso", "aviso": text})
    assert r.status_code == 200
    assert generated.get("/notifications").json()[0]["mensaje"] == text


def test_strict_schema_requires_every_property():
    schema = llm.strict_schema(ai.ConflictAdvice)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"recomendada", "explicacion", "motivos"}
