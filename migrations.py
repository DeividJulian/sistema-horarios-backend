"""
Small schema migrations.

Base.metadata.create_all() only creates tables that do not exist yet; it never adds columns to an
existing table. Columns added to a model after the table was created are added here, on startup.
Every step checks first, so running it many times is safe.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("schedule.migrations")

# (table, column, SQL type and default). Defaults keep the old rows valid.
NEW_COLUMNS = [
    ("grupos", "jornada", "VARCHAR NOT NULL DEFAULT 'todo'"),
    ("aulas", "tipo", "VARCHAR NOT NULL DEFAULT 'general'"),
    ("materias", "tipo_aula", "VARCHAR NOT NULL DEFAULT 'cualquiera'"),
    ("usuarios", "profesor_id", "INTEGER"),
    ("usuarios", "grupo_id", "INTEGER"),
]


def apply_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    for table, column, definition in NEW_COLUMNS:
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column in existing:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        logger.info("Added column %s.%s", table, column)
