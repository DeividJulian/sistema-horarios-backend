"""Email delivery. The provider is chosen with EMAIL_BACKEND:

- consola: writes the email to the terminal (local development, sends nothing).
- memoria: keeps it in OUTBOX (automated tests).
- smtp: an SMTP server, for example Gmail with an app password.
- brevo: Brevo's HTTP API. Works on Render, whose free plan blocks SMTP ports.
"""
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

import config

logger = logging.getLogger("schedule.mailer")

OUTBOX: list[dict] = []
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class MailError(Exception):
    """The provider did not accept the email (credentials, network, unverified sender...)."""


def send_email(to: str, subject: str, text: str, html: str | None = None) -> None:
    backend = config.EMAIL_BACKEND
    if backend == "memoria":
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html})
        return
    if backend == "consola":
        logger.info("Correo para %s | %s\n%s", to, subject, text)
        return

    senders = {"smtp": _send_smtp, "brevo": _send_brevo}
    if backend not in senders:
        raise MailError(f"EMAIL_BACKEND desconocido: {backend}")
    try:
        senders[backend](to, subject, text, html)
    except MailError:
        raise
    except Exception as e:
        logger.error("No se pudo enviar el correo a %s con %s", to, backend, exc_info=e)
        raise MailError(str(e)) from e


def _send_smtp(to: str, subject: str, text: str, html: str | None) -> None:
    message = EmailMessage()
    message["From"] = f"{config.EMAIL_FROM_NAME} <{config.EMAIL_FROM}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
        server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(message)


def _send_brevo(to: str, subject: str, text: str, html: str | None) -> None:
    if not config.BREVO_API_KEY:
        raise MailError("Falta BREVO_API_KEY")
    body = {
        "sender": {"name": config.EMAIL_FROM_NAME, "email": config.EMAIL_FROM},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        body["htmlContent"] = html
    request = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"api-key": config.BREVO_API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            pass
    except urllib.error.HTTPError as e:
        # Brevo explains the reason in the body (unrecognised IP, invalid key, unverified sender...); it never has the key
        detail = e.read().decode("utf-8", "replace")[:300]
        logger.error("Brevo rechazó el correo (%s): %s", e.code, detail)
        raise MailError(f"Brevo respondió {e.code}: {detail}") from e
