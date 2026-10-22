"""Rules of the passwordless login: one-time codes by email, sessions and email delivery."""
import io
import json
import urllib.error
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import config
from database import SessionLocal
from main import app
from models import User, VerificationCode
from security import create_token
from services import codes, mailer
from services.mailer import OUTBOX, MailError
from tests.conftest import ADMIN, last_code, login

ANA = {"nombre": "Ana Ruiz", "email": "ana@mail.com"}


@pytest.fixture
def group_id(client):
    return client.post("/groups", json={"nombre": "Ingeniería 7", "num_estudiantes": 25}).json()["id"]


@pytest.fixture
def ana(group_id):
    return {**ANA, "grupo_id": group_id}


def verify(public, email, code):
    return public.post("/auth/verify", json={"email": email, "codigo": code})


def register(public, body):
    r = public.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    assert verify(public, body["email"], last_code(body["email"])).status_code == 200


def test_register_emails_a_code_and_leaves_the_account_unverified(anonymous_client, ana):
    r = anonymous_client.post("/auth/register", json=ana)
    assert r.status_code == 201 and r.json()["email"] == ANA["email"]
    assert len(OUTBOX) == 1 and OUTBOX[0]["to"] == ANA["email"]
    assert "activar" in OUTBOX[0]["subject"] and last_code(ANA["email"]) in OUTBOX[0]["html"]
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == ANA["email"]).one()
        assert user.verificado is False and user.rol == "estudiante" and user.grupo_id == ana["grupo_id"]


def test_the_code_is_stored_only_as_a_hash(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    code = last_code(ANA["email"])
    with SessionLocal() as db:
        record = db.query(VerificationCode).one()
        assert record.codigo_hash != code and len(record.codigo_hash) == 64 and code not in record.codigo_hash
        assert record.proposito == "registro"


def test_verify_activates_the_account_and_returns_a_session(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    r = verify(anonymous_client, ANA["email"], last_code(ANA["email"]))
    assert r.status_code == 200
    assert r.json()["usuario"]["verificado"] is True and r.json()["usuario"]["rol"] == "estudiante"
    session = TestClient(app, headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert session.get("/auth/me").json()["email"] == ANA["email"]


def test_unverified_account_can_register_again_and_gets_a_new_code(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    first = last_code(ANA["email"])
    r = anonymous_client.post("/auth/register", json={**ana, "nombre": "Ana María Ruiz"})
    assert r.status_code == 201 and len(OUTBOX) == 2
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == ANA["email"]).one().nombre == "Ana María Ruiz"
    second = last_code(ANA["email"])
    if first != second:
        assert verify(anonymous_client, ANA["email"], first).status_code == 400


def test_verified_account_cannot_register_again(anonymous_client, ana):
    register(anonymous_client, ana)
    r = anonymous_client.post("/auth/register", json=ana)
    assert r.status_code == 409 and "Inicia sesión" in r.json()["detail"]


def test_uppercase_emails_are_the_same_account(anonymous_client, ana):
    anonymous_client.post("/auth/register", json={**ana, "email": "  ANA@Mail.COM "})
    assert verify(anonymous_client, "Ana@MAIL.com", last_code(ANA["email"])).status_code == 200
    assert anonymous_client.post("/auth/register", json={**ana, "email": "ANA@MAIL.COM"}).status_code == 409
    assert anonymous_client.post("/auth/login", json={"email": "AnA@mail.com"}).json()["email"] == ANA["email"]


def test_login_emails_a_new_code(anonymous_client, ana):
    register(anonymous_client, ana)
    r = anonymous_client.post("/auth/login", json={"email": ANA["email"]})
    assert r.status_code == 200 and "entrar" in OUTBOX[-1]["subject"]
    assert verify(anonymous_client, ANA["email"], last_code(ANA["email"])).status_code == 200


def test_login_needs_an_existing_account(anonymous_client):
    r = anonymous_client.post("/auth/login", json={"email": "nadie@mail.com"})
    assert r.status_code == 404 and "regístrate" in r.json()["detail"]
    assert OUTBOX == []


def test_wait_between_codes(anonymous_client, ana, monkeypatch):
    monkeypatch.setattr(config, "CODE_WAIT_SECONDS", 30)
    assert anonymous_client.post("/auth/register", json=ana).status_code == 201
    r = anonymous_client.post("/auth/register", json=ana)
    assert r.status_code == 429 and "segundos" in r.json()["detail"]
    assert 0 < int(r.headers["Retry-After"]) <= 30
    assert anonymous_client.post("/auth/login", json={"email": ANA["email"]}).status_code == 429
    assert len(OUTBOX) == 1


def test_wrong_code_says_how_many_attempts_are_left(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    good = last_code(ANA["email"])
    wrong = "000000" if good != "000000" else "111111"
    r = verify(anonymous_client, ANA["email"], wrong)
    assert r.status_code == 400 and r.json()["detail"] == "Código incorrecto. Te quedan 4 intentos."
    assert verify(anonymous_client, ANA["email"], good).status_code == 200


def test_too_many_attempts_burn_the_code(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    good = last_code(ANA["email"])
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(config.CODE_ATTEMPTS - 1):
        verify(anonymous_client, ANA["email"], wrong)
    last = verify(anonymous_client, ANA["email"], wrong)
    assert "Agotaste los intentos" in last.json()["detail"]
    r = verify(anonymous_client, ANA["email"], good)
    assert r.status_code == 400 and r.json()["detail"] == "No hay un código activo: pide uno nuevo."


def test_expired_code(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    with SessionLocal() as db:
        record = db.query(VerificationCode).one()
        record.vence_en = codes.utc_now() - timedelta(seconds=1)
        db.commit()
    r = verify(anonymous_client, ANA["email"], last_code(ANA["email"]))
    assert r.status_code == 400 and r.json()["detail"] == "El código venció: pide uno nuevo."


def test_a_code_works_only_once(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    code = last_code(ANA["email"])
    assert verify(anonymous_client, ANA["email"], code).status_code == 200
    assert verify(anonymous_client, ANA["email"], code).status_code == 400


def test_a_new_code_invalidates_the_previous_one(anonymous_client, ana):
    register(anonymous_client, ana)
    anonymous_client.post("/auth/login", json={"email": ANA["email"]})
    first = last_code(ANA["email"])
    anonymous_client.post("/auth/login", json={"email": ANA["email"]})
    second = last_code(ANA["email"])
    with SessionLocal() as db:
        assert db.query(VerificationCode).filter(VerificationCode.usado.is_(False)).count() == 1
    if first != second:
        assert verify(anonymous_client, ANA["email"], first).status_code == 400
    assert verify(anonymous_client, ANA["email"], second).status_code == 200


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", ""])
def test_malformed_codes_are_rejected(anonymous_client, code):
    assert verify(anonymous_client, ANA["email"], code).status_code == 422


def test_invalid_and_expired_tokens_get_401(client, anonymous_client):
    with SessionLocal() as db:
        admin = db.query(User).filter(User.email == ADMIN["email"]).one()
        expired = create_token(admin, hours=-1)
    for token in ("abc.def.ghi", expired):
        r = TestClient(app, headers={"Authorization": f"Bearer {token}"}).get("/auth/me")
        assert r.status_code == 401 and "Inicia sesión de nuevo" in r.json()["detail"]
    assert anonymous_client.get("/auth/me").status_code == 401


def test_token_signed_with_another_key_is_rejected(client, monkeypatch):
    assert client.get("/auth/me").status_code == 200
    monkeypatch.setattr(config, "SECRET_KEY", "otra-clave-distinta-0123456789abcdef")
    assert client.get("/auth/me").status_code == 401


def test_unverified_account_cannot_use_a_token(anonymous_client, ana):
    anonymous_client.post("/auth/register", json=ana)
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == ANA["email"]).one()
        token = create_token(user)
    session = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    assert session.get("/auth/me").status_code == 401
    assert session.get("/schedules").status_code == 401


def test_if_the_email_fails_nothing_is_saved(anonymous_client, ana, monkeypatch):
    def broken(*args, **kwargs):
        raise MailError("Brevo no respondió")

    monkeypatch.setattr(codes, "send_email", broken)
    r = anonymous_client.post("/auth/register", json=ana)
    assert r.status_code == 502 and "No pudimos enviar el correo" in r.json()["detail"]
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == ANA["email"]).count() == 0
        assert db.query(VerificationCode).count() == 0


def test_if_the_login_email_fails_no_code_is_left(anonymous_client, ana, monkeypatch):
    register(anonymous_client, ana)
    monkeypatch.setattr(codes, "send_email", lambda *a, **k: (_ for _ in ()).throw(MailError("caído")))
    assert anonymous_client.post("/auth/login", json={"email": ANA["email"]}).status_code == 502
    with SessionLocal() as db:
        assert db.query(VerificationCode).filter(VerificationCode.usado.is_(False)).count() == 0


def test_the_first_admin_comes_from_admin_email(monkeypatch):
    from services.users import ensure_admin

    monkeypatch.setattr(config, "ADMIN_EMAIL", "deivid+admin@gmail.com")
    with SessionLocal() as db:
        ensure_admin(db)
        ensure_admin(db)  # running it again does not duplicate it
        admins = db.query(User).filter(User.email == "deivid+admin@gmail.com").all()
        assert len(admins) == 1 and admins[0].rol == "admin" and admins[0].verificado is False
    me = login("deivid+admin@gmail.com").get("/auth/me").json()
    assert me["rol"] == "admin" and me["verificado"] is True


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_brevo_payload(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent.update(url=request.full_url, headers=dict(request.header_items()), body=json.loads(request.data), timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(config, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(config, "BREVO_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(config, "EMAIL_FROM", "deivid@gmail.com")
    monkeypatch.setattr(config, "EMAIL_FROM_NAME", "Horarios y Aulas")
    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake_urlopen)

    mailer.send_email("ana@mail.com", "Asunto", "Texto plano", "<p>HTML</p>")
    assert sent["url"] == "https://api.brevo.com/v3/smtp/email"
    assert sent["headers"]["Api-key"] == "clave-de-prueba"
    assert sent["body"] == {
        "sender": {"name": "Horarios y Aulas", "email": "deivid@gmail.com"},
        "to": [{"email": "ana@mail.com"}],
        "subject": "Asunto",
        "textContent": "Texto plano",
        "htmlContent": "<p>HTML</p>",
    }
    assert sent["timeout"] == 15


def test_brevo_errors_become_mail_errors(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(config, "BREVO_API_KEY", "")
    with pytest.raises(MailError, match="BREVO_API_KEY"):
        mailer.send_email("ana@mail.com", "Asunto", "Texto")

    def refused(request, timeout):
        raise OSError("401 Unauthorized")

    monkeypatch.setattr(config, "BREVO_API_KEY", "clave-mala")
    monkeypatch.setattr(mailer.urllib.request, "urlopen", refused)
    with pytest.raises(MailError):
        mailer.send_email("ana@mail.com", "Asunto", "Texto")


def test_brevo_rejection_reason_is_kept(monkeypatch):
    def blocked(request, timeout):
        body = io.BytesIO(b'{"code":"unauthorized","message":"We have detected you are using an unrecognised IP address"}')
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, body)

    monkeypatch.setattr(config, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(config, "BREVO_API_KEY", "clave")
    monkeypatch.setattr(mailer.urllib.request, "urlopen", blocked)
    with pytest.raises(MailError, match="401.*unrecognised IP"):
        mailer.send_email("ana@mail.com", "Asunto", "Texto")


def test_unknown_email_backend_fails_clearly(monkeypatch):
    monkeypatch.setattr(config, "EMAIL_BACKEND", "paloma")
    with pytest.raises(MailError, match="EMAIL_BACKEND desconocido"):
        mailer.send_email("ana@mail.com", "Asunto", "Texto")
