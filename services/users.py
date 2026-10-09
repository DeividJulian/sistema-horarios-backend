import logging
import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import StudentGroup, Teacher, User
from security import hash_password

logger = logging.getLogger("schedule.auth")

# Accounts that always exist (they are created again if missing when the app starts).
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
    {
        "nombre": "Estudiante de prueba",
        "email": os.getenv("STUDENT_EMAIL", "estudiante@horarios.edu.co"),
        "password": os.getenv("STUDENT_PASSWORD", "Estudiante2026*"),
        "rol": "estudiante",
    },
]

# Every teacher signs in with the email registered for them and this initial password
# (they can change it afterwards from "Cambiar contraseña").
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD", "Profesor2026*")


def ensure_default_users(db: Session) -> None:
    created = []
    for account in DEFAULT_USERS:
        if db.query(User).filter(func.lower(User.email) == account["email"].lower()).first():
            continue
        db.add(
            User(
                nombre=account["nombre"],
                email=account["email"],
                password_hash=hash_password(account["password"]),
                rol=account["rol"],
            )
        )
        created.append(account["email"])
    db.commit()
    if created:
        logger.info("Default users created: %s", ", ".join(created))
    sync_accounts(db)


def sync_accounts(db: Session) -> None:
    """Keeps the accounts in line with the data: one account per teacher, and the demo student in a real group."""
    _sync_teacher_accounts(db)
    _assign_demo_student_group(db)
    db.commit()


def _sync_teacher_accounts(db: Session) -> None:
    teachers = {t.id: t for t in db.query(Teacher).all()}
    accounts = db.query(User).filter(User.rol == "profesor").all()
    linked = {a.profesor_id: a for a in accounts}

    # Accounts of teachers that no longer exist
    for account in accounts:
        if account.profesor_id not in teachers:
            db.delete(account)

    default_hash = None  # hashing is slow on purpose, so the same hash is reused for every new account
    for teacher in teachers.values():
        account = linked.get(teacher.id)
        email_owner = db.query(User).filter(func.lower(User.email) == teacher.email.lower()).first()
        if account is None:
            if email_owner is not None:
                continue  # that email already belongs to another account (for example an administrator)
            default_hash = default_hash or hash_password(TEACHER_PASSWORD)
            db.add(User(nombre=teacher.nombre, email=teacher.email.lower(), password_hash=default_hash, rol="profesor", profesor_id=teacher.id))
            logger.info("Teacher account created: %s", teacher.email)
        else:
            account.nombre = teacher.nombre
            if account.email != teacher.email.lower() and (email_owner is None or email_owner.id == account.id):
                account.email = teacher.email.lower()
    db.flush()


def _assign_demo_student_group(db: Session) -> None:
    email = DEFAULT_USERS[2]["email"].lower()
    student = db.query(User).filter(func.lower(User.email) == email).first()
    if student is None:
        return
    if student.grupo_id is not None and db.get(StudentGroup, student.grupo_id) is not None:
        return
    first_group = db.query(StudentGroup).order_by(StudentGroup.id).first()
    student.grupo_id = first_group.id if first_group else None


def demo_teacher(db: Session) -> Teacher | None:
    """Teacher used for the "Profesor" demo button: the one with the most subjects."""
    from models import Subject

    row = (
        db.query(Teacher)
        .join(Subject, Subject.profesor_id == Teacher.id)
        .group_by(Teacher.id)
        .order_by(func.count(Subject.id).desc(), Teacher.id)
        .first()
    )
    return row or db.query(Teacher).order_by(Teacher.id).first()
