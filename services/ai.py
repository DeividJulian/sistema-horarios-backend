"""
AI layer: Claude explains, in plain Spanish, why the schedule cannot be generated or what is wrong with it, and
suggests concrete fixes. It only reads the data the system already computed (diagnostics, conflicts, statistics);
it never changes anything.

It needs ANTHROPIC_API_KEY in the server environment (Render). Without it the feature reports itself as unavailable
and the rest of the system works the same.
"""
import json
import logging
import os

import anthropic
from sqlalchemy.orm import Session

from models import ScheduleEntry
from services.conflicts import detect_conflicts
from services.readiness import check_readiness
from services.stats import compute_statistics

logger = logging.getLogger("schedule.ai")

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5-5")
# Explanations, not hard reasoning: medium effort keeps answers quick (it is also this model's default, set explicitly)
EFFORT = os.getenv("ANTHROPIC_EFFORT", "medium")
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 90.0
MAX_CONFLICTS_IN_PROMPT = 40

SYSTEM_PROMPT = """Eres el asistente de un sistema universitario que genera horarios automáticamente.
El sistema usa un algoritmo CSP (backtracking) que respeta: disponibilidad de cada profesor, jornada de cada grupo
(mañana, tarde, noche o todo el día), aforo y tipo de aula (general, sala de informática, laboratorio), sin cruces de
profesor, aula ni grupo, máximo 4 horas de clase por grupo y día, y cada materia en días distintos. Después, un
recocido simulado reduce las horas muertas.

Te paso, en JSON, el diagnóstico del sistema, los conflictos detectados y estadísticas del horario actual.
Explica la situación a un administrador académico que no es programador:

1. Un resumen de una o dos frases: ¿se puede generar el horario?, ¿hay problemas?
2. Las causas, en orden de importancia, nombrando los profesores, grupos, materias o aulas involucrados.
3. Sugerencias concretas y accionables, numeradas (por ejemplo: «Agrega a Juan Pérez disponibilidad el martes de
   6:00 p. m. a 9:00 p. m.» o «Crea un laboratorio con aforo de al menos 35»), indicando en qué sección de la
   aplicación se hace (Gestión → Profesores, Aulas, Grupos o Materias).

Usa solo los datos recibidos; no inventes nombres ni cifras. Si todo está bien, dilo y sugiere mejoras opcionales
(por ejemplo, reducir horas muertas o balancear la carga de los profesores). Responde en español, en texto claro con
títulos cortos y viñetas, sin tablas ni bloques de código, y en no más de unas 350 palabras."""


class AIUnavailable(Exception):
    """There is no API key, so the AI layer is off."""


class AIError(Exception):
    """Claude could not answer (network, limits, refusal...). The message is for the user."""


def is_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _client() -> anthropic.Anthropic:
    # Reads ANTHROPIC_API_KEY from the environment; retries 429/5xx and connection errors twice by itself
    return anthropic.Anthropic(timeout=TIMEOUT_SECONDS, max_retries=2)


def build_context(db: Session) -> dict:
    """Everything the system knows about the schedule, trimmed to what helps explain it."""
    readiness = check_readiness(db)
    conflicts = detect_conflicts(db)
    stats = compute_statistics(db)
    return {
        "diagnostico": readiness,
        "hay_horario": db.query(ScheduleEntry).first() is not None,
        "conflictos": {
            "total": len(conflicts),
            "lista": conflicts[:MAX_CONFLICTS_IN_PROMPT],
        },
        "estadisticas": {
            "totales": stats.get("totales"),
            "cumplimiento": stats.get("cumplimiento"),
            "ocupacion_aulas": stats.get("ocupacion_aulas"),
            "carga_profesores": stats.get("carga_profesores"),
        },
    }


def explain(db: Session, question: str | None = None) -> dict:
    """Asks Claude for an explanation and suggestions. Returns {"explicacion", "modelo"}."""
    if not is_available():
        raise AIUnavailable()

    context = build_context(db)
    user_text = "Datos del sistema:\n" + json.dumps(context, ensure_ascii=False, default=str)
    if question:
        user_text += f"\n\nPregunta del administrador: {question}"

    try:
        response = _client().beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            output_config={"effort": EFFORT},
            # If a safety classifier declines, the API retries the same request on a fallback model by itself
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": user_text}],
        )
    except anthropic.AuthenticationError:
        logger.error("Claude rejected the API key")
        raise AIError("La clave de la IA no es válida. Revisa ANTHROPIC_API_KEY en el servidor.")
    except anthropic.RateLimitError:
        raise AIError("La IA está recibiendo demasiadas consultas. Intenta de nuevo en un minuto.")
    except anthropic.APITimeoutError:
        raise AIError("La IA tardó demasiado en responder. Intenta de nuevo.")
    except anthropic.APIConnectionError:
        raise AIError("No se pudo conectar con la IA. Intenta de nuevo en un momento.")
    except anthropic.APIStatusError as error:
        logger.error("Claude API error %s: %s", error.status_code, error.message)
        raise AIError("La IA no pudo responder en este momento. Intenta de nuevo más tarde.")

    if response.stop_reason == "refusal":
        logger.warning("Claude declined the request: %s", getattr(response, "stop_details", None))
        raise AIError("La IA no pudo responder esta consulta.")

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise AIError("La IA no devolvió una respuesta. Intenta de nuevo.")
    logger.info("Claude explanation: %s tokens in, %s out", response.usage.input_tokens, response.usage.output_tokens)
    return {"explicacion": text, "modelo": response.model}
