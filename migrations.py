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


def apply_migrations(engine: Engine) -> None:
    columns = {c["name"] for c in inspect(engine).get_columns("grupos")}
    if "jornada" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE grupos ADD COLUMN jornada VARCHAR NOT NULL DEFAULT 'todo'"))
        logger.info("Added column grupos.jornada (default 'todo')")
