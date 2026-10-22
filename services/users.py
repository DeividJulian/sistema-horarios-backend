import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

import config
from models import Teacher, User

logger = logging.getLogger("schedule.auth")


def ensure_admin(db: Session) -> None:
    """With ADMIN_EMAIL set, creates that administrator if the account doesn't exist yet.

    There is no password: the administrator enters with a code sent to that email, so it must be a real inbox.
    """
    email = config.ADMIN_EMAIL
    if not email:
        return
    if db.query(User).filter(func.lower(User.email) == email).first():
        return
    db.add(User(nombre=config.ADMIN_NAME, email=email, rol="admin"))
    db.commit()
    logger.info("Administrador inicial creado: %s (entra con el código que llega a ese correo)", email)


def sync_accounts(db: Session) -> None:
    """Keeps one account per teacher, with the email the administrator registered for them."""
    teachers = {t.id: t for t in db.query(Teacher).all()}
    accounts = db.query(User).filter(User.rol == "profesor").all()
    linked = {a.profesor_id: a for a in accounts}

    # Accounts of teachers that no longer exist
    for account in accounts:
        if account.profesor_id not in teachers:
            db.delete(account)

    for teacher in teachers.values():
        account = linked.get(teacher.id)
        email_owner = db.query(User).filter(func.lower(User.email) == teacher.email.lower()).first()
        if account is None:
            if email_owner is not None:
                continue  # that email already belongs to another account (for example an administrator)
            # The teacher enters with a code sent to this email; the first code verifies the account
            db.add(User(nombre=teacher.nombre, email=teacher.email.lower(), rol="profesor", profesor_id=teacher.id))
            logger.info("Teacher account created: %s", teacher.email)
        else:
            account.nombre = teacher.nombre
            if account.email != teacher.email.lower() and (email_owner is None or email_owner.id == account.id):
                account.email = teacher.email.lower()
    db.commit()
