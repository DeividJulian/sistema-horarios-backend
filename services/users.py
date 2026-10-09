import logging
import os

from sqlalchemy.orm import Session

from models import User
from security import hash_password

logger = logging.getLogger("schedule.auth")

# Accounts created the first time the app starts with an empty users table.
# Their emails and passwords can be changed with these environment variables.
DEFAULT_USERS = [
    {
        "nombre": "Administrador",
        "email": os.getenv("ADMIN_EMAIL", "admin@horarios.edu.co"),
        "password": os.getenv("ADMIN_PASSWORD", "Admin2026*"),
        "rol": "admin",
    },
    {
        "nombre": "Usuario de consulta",
        "email": os.getenv("USER_EMAIL", "usuario@horarios.edu.co"),
        "password": os.getenv("USER_PASSWORD", "Usuario2026*"),
        "rol": "usuario",
    },
]


def ensure_default_users(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    for account in DEFAULT_USERS:
        db.add(
            User(
                nombre=account["nombre"],
                email=account["email"],
                password_hash=hash_password(account["password"]),
                rol=account["rol"],
            )
        )
    db.commit()
    logger.info("Default users created: %s", ", ".join(a["email"] for a in DEFAULT_USERS))
