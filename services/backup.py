"""
Copy of the real data taken before the demo data replaces it, and the way back.

Only one copy is kept: the first one. If the demo is loaded again over the demo, the copy still holds
the original data (otherwise a second demo load would overwrite it with demo data).
"""
import json
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Time, text
from sqlalchemy.orm import Session

from models import (
    Backup,
    Cancellation,
    Classroom,
    Notification,
    ScheduleEntry,
    StudentGroup,
    Subject,
    Teacher,
    TeacherAvailability,
    User,
)
from services.seed import delete_all
from services.users import sync_accounts
from time_format import as_utc

# Insertion order: a table only refers to the ones before it
MODELS = [Teacher, TeacherAvailability, Classroom, StudentGroup, Subject, ScheduleEntry, Cancellation, Notification]


def _dump(row) -> dict:
    data = {}
    for column in row.__table__.columns:
        value = getattr(row, column.key)
        data[column.name] = value.isoformat() if isinstance(value, (date, time, datetime)) else value
    return data


def _load(model, data: dict):
    values = {}
    for column in model.__table__.columns:
        if column.name not in data:
            continue
        value = data[column.name]
        if value is not None:
            if isinstance(column.type, DateTime):
                value = datetime.fromisoformat(value)
            elif isinstance(column.type, Date):
                value = date.fromisoformat(value)
            elif isinstance(column.type, Time):
                value = time.fromisoformat(value)
        values[column.key] = value
    return model(**values)


def _summary(db: Session) -> dict:
    return {
        "profesores": db.query(Teacher).count(),
        "aulas": db.query(Classroom).count(),
        "grupos": db.query(StudentGroup).count(),
        "materias": db.query(Subject).count(),
        "bloques": db.query(ScheduleEntry).count(),
    }


def save_backup(db: Session) -> bool:
    """Saves the current data unless a copy already exists. Returns True if a copy was taken."""
    if db.query(Backup).first() is not None:
        return False
    content = {
        "resumen": _summary(db),
        "tablas": {m.__tablename__: [_dump(r) for r in db.query(m).order_by(m.id)] for m in MODELS},
        # Teacher accounts are deleted with the teachers; students lose their group
        "usuarios": {
            "profesores": [_dump(u) for u in db.query(User).filter(User.rol == "profesor")],
            "grupos_estudiantes": {str(u.id): u.grupo_id for u in db.query(User).filter(User.grupo_id.isnot(None))},
        },
    }
    db.add(Backup(contenido=json.dumps(content, ensure_ascii=False)))
    db.commit()
    return True


def backup_info(db: Session) -> dict:
    backup = db.query(Backup).first()
    if backup is None:
        return {"existe": False}
    return {"existe": True, "creado_en": as_utc(backup.creado_en), "resumen": json.loads(backup.contenido)["resumen"]}


def discard_backup(db: Session) -> None:
    db.query(Backup).delete()
    db.commit()


def restore_backup(db: Session) -> dict | None:
    """Replaces the current data with the copy, ids included (users keep pointing to their group). None if there is no copy."""
    backup = db.query(Backup).first()
    if backup is None:
        return None
    content = json.loads(backup.contenido)

    delete_all(db)  # also removes the teacher accounts of the demo
    for model in MODELS:
        for data in content["tablas"].get(model.__tablename__, []):
            db.add(_load(model, data))
        db.flush()

    taken = {uid for (uid,) in db.query(User.id)}
    for data in content["usuarios"]["profesores"]:
        account = _load(User, data)
        if account.id in taken:
            account.id = None  # very unlikely: the id was reused, so the account gets a new one
        db.add(account)
    db.flush()
    for user_id, group_id in content["usuarios"]["grupos_estudiantes"].items():
        user = db.get(User, int(user_id))
        if user is not None and user.rol == "estudiante":
            user.grupo_id = group_id

    db.delete(backup)
    db.commit()
    _reset_sequences(db)
    sync_accounts(db)
    return content["resumen"]


def _reset_sequences(db: Session) -> None:
    """PostgreSQL does not move the id counters when rows are inserted with their own id."""
    if db.get_bind().dialect.name != "postgresql":
        return
    for table in [m.__tablename__ for m in MODELS] + [User.__tablename__]:
        db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            )
        )
    db.commit()
