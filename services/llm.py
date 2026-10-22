"""Provider-independent client for the language model, with schema-validated (structured) outputs.

Every provider is called through its OpenAI-compatible endpoint (POST {base_url}/chat/completions).

Environment variables (read on every call, so changing them needs no code change):
  AI_PROVIDER        groq | gemini | openai (default groq)
  AI_API_KEY         API key of that provider (required to use the AI features)
  AI_MODEL           optional model override (each provider has a default)
  AI_BASE_URL        optional endpoint override (each provider has a default)
  AI_FALLBACK_MODEL  optional lighter model used when the main one is busy, out of quota or too slow
"""
import copy
import dataclasses
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("schedule.ai")

TIMEOUT_SECONDS = 30
# With a fallback model, the main one gets less time: when it is busy it is often just slow
PRIMARY_TIMEOUT_SECONDS = 15
RETRYABLE_STATUS = {500, 502, 503, 504}
RETRY_DELAY_SECONDS = 1.5


@dataclass(frozen=True)
class Provider:
    label: str
    default_model: str
    default_base_url: str


PROVIDERS = {
    "groq": Provider("Groq", "openai/gpt-oss-20b", "https://api.groq.com/openai/v1"),
    "gemini": Provider("Gemini (Google)", "gemini-flash-latest", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    "openai": Provider("OpenAI", "gpt-5-mini", "https://api.openai.com/v1"),
}
DEFAULT_PROVIDER = "groq"

T = TypeVar("T", bound=BaseModel)


class LLMNotConfigured(Exception):
    """There is no API key (or the provider name is unknown). The message is shown to the user."""


class LLMError(Exception):
    """The provider failed or returned an unusable answer. The message is shown to the user, so it is in Spanish."""


class LLMUnavailable(LLMError):
    """The provider is overloaded (5xx) or did not answer in time: another model may still work."""


class LLMRateLimited(LLMError):
    """The provider's usage limit was reached (HTTP 429). retry_after: seconds to wait, if the provider said."""

    def __init__(self, message: str, retry_after: str | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True)
class AIConfig:
    provider: str
    api_key: str
    model: str
    base_url: str
    fallback_model: str | None = None

    @property
    def label(self) -> str:
        spec = PROVIDERS.get(self.provider)
        return spec.label if spec else self.provider


def current_config() -> AIConfig:
    provider = (os.getenv("AI_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    spec = PROVIDERS.get(provider)
    model = (os.getenv("AI_MODEL") or "").strip() or (spec.default_model if spec else "")
    base_url = (os.getenv("AI_BASE_URL") or "").strip() or (spec.default_base_url if spec else "")
    fallback = (os.getenv("AI_FALLBACK_MODEL") or "").strip()
    if fallback.lower() in ("", "none", "no", "false") or fallback == model:
        fallback = None
    return AIConfig(provider, (os.getenv("AI_API_KEY") or "").strip(), model, base_url, fallback)


def is_configured() -> bool:
    config = current_config()
    return config.provider in PROVIDERS and bool(config.api_key)


def _check(config: AIConfig) -> None:
    if config.provider not in PROVIDERS:
        raise LLMNotConfigured(f"AI_PROVIDER no es válido: usa uno de {', '.join(PROVIDERS)}")
    if not config.api_key:
        raise LLMNotConfigured("falta AI_API_KEY en el servidor")


def _status_error(config: AIConfig, status: int, retry_after: str | None = None) -> LLMError:
    """Same Spanish message for the same problem, whatever the provider."""
    name = config.label
    if status == 429:
        return LLMRateLimited(f"Se alcanzó el límite de uso de {name}. Espera unos minutos y vuelve a intentarlo.", retry_after)
    if status in (401, 403):
        return LLMError(f"La clave de {name} no es válida o no tiene permisos (revisa AI_API_KEY).")
    if status == 404:
        return LLMError(f"{name} no reconoce el modelo configurado (revisa AI_MODEL).")
    if status >= 500:
        return LLMUnavailable(f"El servicio de {name} no está disponible en este momento ({status}). Intenta más tarde.")
    return LLMError(f"{name} rechazó la solicitud ({status}).")


def strict_schema(output_type: type[BaseModel]) -> dict[str, Any]:
    """JSON schema of a Pydantic model in the strict form of OpenAI-style structured outputs:
    every object lists all its properties as required and allows no extra ones."""
    schema = copy.deepcopy(output_type.model_json_schema())

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and isinstance(node.get("properties"), dict):
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


def _without_code_fence(text: str) -> str:
    """Some models wrap the JSON in ```json ... ``` even when asked for raw JSON."""
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)


def _post(config: AIConfig, body: dict, timeout: float) -> tuple[int, dict, str]:
    """POST to the provider. Returns (status, headers, text); network problems become LLM errors."""
    request = urllib.request.Request(
        config.base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()) if e.headers else {}, e.read().decode("utf-8", "replace")
    except (TimeoutError, socket.timeout) as e:
        raise LLMUnavailable(f"{config.label} tardó demasiado en responder. Intenta de nuevo.") from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise LLMUnavailable(f"{config.label} tardó demasiado en responder. Intenta de nuevo.") from e
        raise LLMError(f"No se pudo contactar a {config.label}.") from e
    except OSError as e:
        raise LLMError(f"No se pudo contactar a {config.label}.") from e


def _generate(config: AIConfig, system: str, user: str, output_type: type[T], retry: bool = True,
              timeout: float = TIMEOUT_SECONDS) -> T:
    body = {
        "model": config.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": output_type.__name__.lower(), "strict": True, "schema": strict_schema(output_type)},
        },
    }
    for attempt in range(2 if retry else 1):
        status, headers, text = _post(config, body, timeout)
        # A busy provider (5xx) often answers on a second try; usage limits (429) are not retried
        if status in RETRYABLE_STATUS and retry and attempt == 0:
            logger.info("El proveedor %s respondió %s: se reintenta una vez", config.provider, status)
            time.sleep(RETRY_DELAY_SECONDS)
            continue
        break
    if status != 200:
        # The provider's message helps to diagnose (it never contains the API key)
        logger.warning("El proveedor %s respondió %s: %s", config.provider, status, text[:300])
        retry_after = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
        raise _status_error(config, status, retry_after)

    try:
        choice = json.loads(text)["choices"][0]
        message = choice["message"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise LLMError("La IA no devolvió una respuesta válida.") from e
    if message.get("refusal") or choice.get("finish_reason") == "content_filter":
        raise LLMError("La IA declinó responder esta consulta.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise LLMError("La IA no devolvió una respuesta válida.")
    try:
        return output_type.model_validate_json(_without_code_fence(content))
    except ValidationError as e:
        raise LLMError("La IA no devolvió una respuesta válida.") from e


def generate(system: str, user: str, output_type: type[T]) -> T:
    """Asks the model for an answer that must match output_type's schema, and returns it validated."""
    config = current_config()
    _check(config)
    if not config.fallback_model:
        return _generate(config, system, user, output_type)
    # One try with the main model; if it is busy, out of quota or slow, the lighter model answers instead
    try:
        return _generate(config, system, user, output_type, retry=False, timeout=PRIMARY_TIMEOUT_SECONDS)
    except (LLMUnavailable, LLMRateLimited) as e:
        logger.info("%s falló (%s): se usa el modelo de respaldo %s", config.model, e, config.fallback_model)
    return _generate(dataclasses.replace(config, model=config.fallback_model), system, user, output_type)
