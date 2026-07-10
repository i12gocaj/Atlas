"""Seleccion del proveedor LLM.

Atlas es 100% local: el unico proveedor de produccion es Ollama. No hay backend
en la nube ni API keys, por diseno (los prompts pueden contener secretos y no
deben salir de la maquina). El StubProvider existe solo para tests y demo de
respaldo.
"""

from __future__ import annotations

from .base import LLMError, LLMProvider
from .config import LLMSettings, load_settings
from .ollama_provider import OllamaProvider


def get_provider(settings: LLMSettings | None = None) -> LLMProvider:
    """Devuelve el proveedor LLM local (Ollama). Falla claro si no esta disponible."""
    settings = settings or load_settings()
    if not OllamaProvider.is_available(settings.ollama_host):
        raise LLMError(
            f"Ollama no responde en {settings.ollama_host}. Arranca el servidor "
            "con 'ollama serve' y asegurate de tener el modelo descargado "
            f"('ollama pull {settings.ollama_model}')."
        )
    return OllamaProvider(settings.ollama_model, settings.ollama_host)


def describe_provider(provider: LLMProvider) -> str:
    """Cadena legible para mostrar que proveedor y modelo se esta usando."""
    return f"{provider.name}:{provider.model}"
