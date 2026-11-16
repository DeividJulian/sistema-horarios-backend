"""Settings read from environment variables (.env file locally, Render dashboard in production)."""
import hashlib
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("schedule.config")

# Signs the session tokens and the one-time codes. JWT_SECRET is the old name and still works.
# Without either, the key is derived from DATABASE_URL, which is already private and stable across restarts
# (a random one would log everybody out on every Render restart).
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET") or ""
if not SECRET_KEY:
    SECRET_KEY = hashlib.sha256(f"jwt::{os.getenv('DATABASE_URL')}".encode()).hexdigest()
    logger.warning("SECRET_KEY no está configurada: se deriva de DATABASE_URL (configúrala en producción)")
TOKEN_HOURS = float(os.getenv("TOKEN_HORAS", "8"))

# One-time codes sent by email
CODE_MINUTES = int(os.getenv("CODIGO_MINUTOS", "10"))
CODE_ATTEMPTS = int(os.getenv("CODIGO_INTENTOS", "5"))
CODE_WAIT_SECONDS = int(os.getenv("CODIGO_ESPERA_SEGUNDOS", "30"))

# Email delivery: consola | memoria | smtp | brevo
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "consola").strip().lower()
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@horarios.local")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Horarios y Aulas")
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# First administrator: created at startup with this email if the account doesn't exist yet
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
ADMIN_NAME = os.getenv("ADMIN_NAME") or "Administrador"

# Demo accounts for presenting the project: they enter with a password instead of an emailed code, because
# their inboxes are not ours. The password is public on purpose (it is in the README); DEMO_ACCOUNTS=false
# turns both accounts off after the presentation.
DEMO_ACCOUNTS = os.getenv("DEMO_ACCOUNTS", "true").strip().lower() not in ("0", "false", "no", "")
DEMO_ADMIN_EMAIL = (os.getenv("DEMO_ADMIN_EMAIL") or "administrador@gmail.com").strip().lower()
DEMO_TEACHER_EMAIL = (os.getenv("DEMO_TEACHER_EMAIL") or "profesor@gmail.com").strip().lower()
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD") or "demo123"


def demo_emails() -> set[str]:
    """Emails that enter with the demo password (none when the demo accounts are off)."""
    return {DEMO_ADMIN_EMAIL, DEMO_TEACHER_EMAIL} if DEMO_ACCOUNTS else set()
