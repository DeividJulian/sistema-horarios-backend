"""Keeps people's personal data (names, emails, phones) away from the external AI provider.

Teachers travel to the model as "Docente A", "Docente B"...; their real names are put back only in the answer
shown to the user. Emails and phone numbers in free text (for example a cancellation reason) are hidden.
"""
import re
import string

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")

# Each letter also matches its accented forms, so "Julian" in a text hides "Julián" and vice versa
_ACCENTS = {"a": "aáàä", "e": "eéèë", "i": "iíìï", "o": "oóòö", "u": "uúùü", "n": "nñ"}
_PLAIN = {accented: plain for plain, group in _ACCENTS.items() for accented in group}


def _word_pattern(word: str) -> re.Pattern:
    letters = "".join(
        f"[{_ACCENTS[_PLAIN.get(c, c)]}]" if _PLAIN.get(c, c) in _ACCENTS else re.escape(c) for c in word.lower()
    )
    return re.compile(rf"(?<!\w){letters}(?!\w)", re.IGNORECASE)


class Aliases:
    """Neutral names for the teachers of one AI request."""

    def __init__(self):
        self._alias_by_name: dict[str, str] = {}

    def alias(self, name: str) -> str:
        if name not in self._alias_by_name:
            n = len(self._alias_by_name)
            letter = string.ascii_uppercase[n % 26] + (str(n // 26) if n >= 26 else "")
            self._alias_by_name[name] = f"Docente {letter}"
        return self._alias_by_name[name]

    def redact(self, text: str) -> str:
        """Hides emails, phones and every known name (whole name first, then each part of three letters or more)."""
        result = _EMAIL.sub("[correo]", text or "")
        result = _PHONE.sub("[teléfono]", result)
        for name, alias in sorted(self._alias_by_name.items(), key=lambda item: -len(item[0])):
            whole = r"\s+".join(_word_pattern(part).pattern for part in name.split())
            result = re.sub(whole, alias, result, flags=re.IGNORECASE)
        for name, alias in self._alias_by_name.items():
            for part in name.split():
                if len(part) >= 3:
                    result = _word_pattern(part).sub(alias, result)
        return result

    def restore(self, text: str) -> str:
        """Puts the real names back in the model's answer, which only the signed-in user sees."""
        result = text or ""
        for name, alias in sorted(self._alias_by_name.items(), key=lambda item: -len(item[1])):
            result = re.sub(rf"\b{re.escape(alias)}\b", name, result)
        return result
