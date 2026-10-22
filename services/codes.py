"""Passwordless login: one-time six-digit codes sent by email."""
import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import func
from sqlalchemy.orm import Session

import config
from models import User, VerificationCode
from services.mailer import send_email


class CodeCooldown(Exception):
    def __init__(self, seconds: int):
        self.seconds = seconds
        super().__init__(f"Espera {seconds} segundos antes de pedir otro código.")


class InvalidCode(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime) -> datetime:
    """SQLite returns dates without a time zone: they are UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _hash(user_id: int, code: str) -> str:
    # The user id in the message makes the same code hash differently for each account
    return hmac.new(config.SECRET_KEY.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_user(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()


def _latest_code(db: Session, user: User, only_active: bool = False) -> VerificationCode | None:
    query = db.query(VerificationCode).filter(VerificationCode.usuario_id == user.id)
    if only_active:
        query = query.filter(VerificationCode.usado.is_(False))
    return query.order_by(VerificationCode.id.desc()).first()


def issue_code(db: Session, user: User, purpose: str) -> str:
    """Creates a new code and invalidates the previous ones, respecting a minimum wait between emails."""
    latest = _latest_code(db, user)
    if latest:
        wait = config.CODE_WAIT_SECONDS - (utc_now() - _aware(latest.creado_en)).total_seconds()
        if wait > 0:
            raise CodeCooldown(math.ceil(wait))

    db.query(VerificationCode).filter(
        VerificationCode.usuario_id == user.id, VerificationCode.usado.is_(False)
    ).update({"usado": True})
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        VerificationCode(
            usuario_id=user.id,
            codigo_hash=_hash(user.id, code),
            proposito=purpose,
            vence_en=utc_now() + timedelta(minutes=config.CODE_MINUTES),
            creado_en=utc_now(),
        )
    )
    db.flush()
    return code


def check_code(db: Session, user: User, code: str) -> None:
    """Validates the latest active code. Raises InvalidCode; the caller must commit to keep the failed attempt."""
    record = _latest_code(db, user, only_active=True)
    if not record:
        raise InvalidCode("No hay un código activo: pide uno nuevo.")
    if _aware(record.vence_en) < utc_now():
        record.usado = True
        raise InvalidCode("El código venció: pide uno nuevo.")
    if not hmac.compare_digest(record.codigo_hash, _hash(user.id, code)):
        record.intentos += 1
        left = config.CODE_ATTEMPTS - record.intentos
        if left <= 0:
            record.usado = True
            raise InvalidCode("Código incorrecto. Agotaste los intentos: pide uno nuevo.")
        raise InvalidCode(f"Código incorrecto. Te quedan {left} {'intento' if left == 1 else 'intentos'}.")
    record.usado = True


def send_code(user: User, code: str, purpose: str) -> None:
    action = "activar tu cuenta" if purpose == "registro" else "iniciar sesión"
    subject = (
        "Tu código para activar Horarios y Aulas" if purpose == "registro" else "Tu código para entrar a Horarios y Aulas"
    )
    text = (
        f"Hola, {user.nombre}:\n\n"
        f"Usa este código para {action}: {code}\n\n"
        f"Vence en {config.CODE_MINUTES} minutos. Si no lo pediste, ignora este correo.\n\n"
        "Horarios y Aulas · Universidad Cooperativa de Colombia"
    )
    html = (
        f"<p>Hola, {escape(user.nombre)}:</p>"
        f"<p>Usa este código para {action}:</p>"
        f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{code}</p>'
        f"<p>Vence en {config.CODE_MINUTES} minutos. Si no lo pediste, ignora este correo.</p>"
        "<p>Horarios y Aulas · Universidad Cooperativa de Colombia</p>"
    )
    send_email(user.email, subject, text, html)
