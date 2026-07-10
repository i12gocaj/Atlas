"""Proveedor LLM de pruebas (stub), determinista y sin red.

Permite testear toda la capa de analisis sin un modelo real: se le pasa una
funcion que, dado (prompt, system), devuelve el texto de respuesta. Util tambien
para una demo de respaldo si no hubiera ni Ollama ni red.
"""

from __future__ import annotations

from typing import Callable

from .base import LLMProvider

Responder = Callable[[str, str | None], str]


class StubProvider(LLMProvider):
    """Proveedor que delega en una funcion para producir respuestas canned."""

    name = "stub"

    def __init__(self, responder: Responder, model: str = "stub") -> None:
        self.model = model
        self._responder = responder
        self.calls: list[dict] = []

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system, "json_mode": json_mode})
        return self._responder(prompt, system)
