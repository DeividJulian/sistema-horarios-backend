"""How hours and dates are written in messages for the user: 12-hour clock with a. m. / p. m. (Colombian style)."""
from datetime import date, datetime, timezone

WEEKDAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def format_hour(hour: int) -> str:
    """18 -> "6:00 p. m.", 8 -> "8:00 a. m.", 12 -> "12:00 p. m.", 0 -> "12:00 a. m."."""
    suffix = "a. m." if hour < 12 else "p. m."
    return f"{hour % 12 or 12}:00 {suffix}"


def format_range(start: int, end: int) -> str:
    """(18, 22) -> "6:00 p. m. a 10:00 p. m."."""
    return f"{format_hour(start)} a {format_hour(end)}"


def format_date(value: date) -> str:
    """date(2026, 10, 13) -> "martes 13 de octubre"."""
    return f"{WEEKDAY_NAMES[value.weekday()]} {value.day} de {MONTH_NAMES[value.month - 1]}"


def as_utc(value: datetime) -> datetime:
    """SQLite gives back timestamps without time zone (they are UTC); the browser needs to know it."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
