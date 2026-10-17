"""The AI layer is tested with a fake Claude client: no real API calls, no cost."""
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from services import ai
from tests.conftest import STUDENT


class FakeClient:
    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response
        self._error = error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def _answer(text="## Resumen\nTodo bien.", stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=None,
        model="claude-opus-5-5",
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
    )


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")


def test_without_key_the_ai_is_off(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/ai/status").json() == {"disponible": False, "modelo": None}
    r = client.post("/ai/explain")
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_explains_with_the_real_schedule_data(client, demo_data, with_key, monkeypatch):
    fake = FakeClient(_answer("## Resumen\nEl horario está completo."))
    monkeypatch.setattr(ai, "_client", lambda: fake)
    client.post("/schedules/generate")

    assert client.get("/ai/status").json() == {"disponible": True, "modelo": "claude-opus-5-5"}
    r = client.post("/ai/explain", json={"pregunta": "¿Puedo reducir las horas muertas?"})
    assert r.status_code == 200, r.text
    assert r.json() == {"explicacion": "## Resumen\nEl horario está completo.", "modelo": "claude-opus-5-5"}

    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]
    prompt = call["messages"][0]["content"]
    assert '"diagnostico"' in prompt and '"conflictos"' in prompt and '"cumplimiento"' in prompt
    assert "Carlos Mendoza" in prompt  # names from the database reach Claude
    assert "¿Puedo reducir las horas muertas?" in prompt


def test_conflicts_are_part_of_the_context(client, demo_data, with_key, monkeypatch, db):
    fake = FakeClient(_answer())
    monkeypatch.setattr(ai, "_client", lambda: fake)
    client.post("/schedules/generate")
    # Break the schedule: a subject loses all its blocks, so the hours are incomplete
    subject = client.get("/subjects").json()[0]
    for entry in client.get("/schedules").json():
        if entry["materia_id"] == subject["id"]:
            client.delete(f"/schedules/{entry['id']}")
    client.post("/ai/explain")
    assert "intensidad_incorrecta" in fake.calls[0]["messages"][0]["content"]


def test_a_refusal_is_reported_clearly(client, with_key, monkeypatch):
    monkeypatch.setattr(ai, "_client", lambda: FakeClient(_answer("", stop_reason="refusal")))
    r = client.post("/ai/explain")
    assert r.status_code == 502 and r.json()["detail"] == "La IA no pudo responder esta consulta."


def test_api_errors_become_messages_for_the_user(client, with_key, monkeypatch):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    monkeypatch.setattr(ai, "_client", lambda: FakeClient(error=anthropic.APIConnectionError(request=request)))
    r = client.post("/ai/explain")
    assert r.status_code == 502 and "No se pudo conectar con la IA" in r.json()["detail"]


def test_students_cannot_use_it(anonymous_client, with_key):
    token = anonymous_client.post("/auth/login", json={"email": STUDENT["email"], "password": STUDENT["password"]}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert anonymous_client.get("/ai/status", headers=headers).status_code == 403
    assert anonymous_client.post("/ai/explain", headers=headers).status_code == 403
