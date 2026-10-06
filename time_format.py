"""How hours are written in messages for the user: 12-hour clock with a. m. / p. m. (Colombian style)."""


def format_hour(hour: int) -> str:
    """18 -> "6:00 p. m.", 8 -> "8:00 a. m.", 12 -> "12:00 p. m.", 0 -> "12:00 a. m."."""
    suffix = "a. m." if hour < 12 else "p. m."
    return f"{hour % 12 or 12}:00 {suffix}"


def format_range(start: int, end: int) -> str:
    """(18, 22) -> "6:00 p. m. a 10:00 p. m."."""
    return f"{format_hour(start)} a {format_hour(end)}"
