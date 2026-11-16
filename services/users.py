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


def ensure_demo_accounts(db: Session) -> None:
    """With DEMO_ACCOUNTS on, makes sure the demo administrator exists and, if there are teachers but none uses
    the demo teacher email, adds a demo teacher (sync_accounts then creates its account).

    On an empty database no teacher is created, so the first data load is not blocked: the demo and faculty
    datasets already give the demo email to one of their teachers.
    """
    if not config.DEMO_ACCOUNTS:
        return
    admin = db.query(User).filter(func.lower(User.email) == config.DEMO_ADMIN_EMAIL).first()
    if admin is None:
        db.add(User(nombre="Administrador (demo)", email=config.DEMO_ADMIN_EMAIL, rol="admin", verificado=True))
        logger.info("Cuenta de demostración creada: %s (administrador)", config.DEMO_ADMIN_EMAIL)
    teachers = db.query(Teacher).count()
    demo_teacher = db.query(Teacher).filter(func.lower(Teacher.email) == config.DEMO_TEACHER_EMAIL).first()
    if teachers and demo_teacher is None:
        db.add(Teacher(nombre="Profesor (demo)", email=config.DEMO_TEACHER_EMAIL))
        logger.info("Profesor de demostración creado: %s", config.DEMO_TEACHER_EMAIL)
    db.commit()


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
