"""Interfaz comun de proveedores LLM y utilidades de parseo.

Toda la capa de analisis (clasificador, detector de secretos, brief) depende de
esta interfaz, no de un proveedor concreto. Asi podemos cambiar de modelo local
o usar un stub en los tests, sin tocar nada mas.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class LLMError(RuntimeError):
    """Error al hablar con un proveedor LLM."""


class LLMProvider(ABC):
    """Proveedor de generacion de texto. Implementaciones: Ollama, Stub."""

    name: str = "base"
    model: str = "unknown"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        """Genera una respuesta de texto a partir de un prompt."""

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Genera y parsea una respuesta JSON. Robusto a fences y texto extra."""
        text = self.generate(prompt, system=system, json_mode=True, temperature=temperature)
        return extract_json(text)


def extract_json(text: str) -> dict[str, Any]:
    """Extrae un objeto JSON de la respuesta del modelo.

    Tolera bloques de codigo (```json ... ```) y texto antes o despues del objeto.
    """
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(cleaned)
        # Los llamadores esperan un objeto; un array u otro tipo valido debe
        # degradar como LLMError (fallback controlado), no reventar con .get().
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Fallback: primer { hasta el ultimo } equilibrado. Rescata tambien el caso
    # de un array con un unico objeto dentro.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"No se pudo parsear JSON del modelo: {exc}\nTexto: {cleaned[:300]}")
        if isinstance(parsed, dict):
            return parsed
    raise LLMError(f"La respuesta del modelo no es un objeto JSON.\nTexto: {cleaned[:300]}")
