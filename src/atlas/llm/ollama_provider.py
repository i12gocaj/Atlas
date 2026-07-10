"""Proveedor LLM local via Ollama.

Habla con el servidor local de Ollama por HTTP (sin dependencias externas, solo
urllib). Es el proveedor por defecto: privado (los prompts no salen de la
maquina) y sin dependencia de red en la demo.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

from .base import LLMError, LLMProvider

_TIMEOUT_SECONDS = 180


class OllamaProvider(LLMProvider):
    """Genera texto con un modelo servido por Ollama en local."""

    name = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (OSError, http.client.HTTPException) as exc:
            # OSError cubre URLError, TimeoutError y ConnectionError: urllib solo
            # envuelve en URLError los fallos de conexion, no el timeout mientras
            # se ESPERA la respuesta (getresponse), que con stream:false es justo
            # donde expira (modelo cargando en frio).
            raise LLMError(f"No se pudo contactar con Ollama en {self.host}: {exc}")
        except json.JSONDecodeError as exc:
            raise LLMError(f"Respuesta invalida de Ollama: {exc}")

        content = body.get("message", {}).get("content", "")
        if not content:
            raise LLMError("Ollama devolvio una respuesta vacia (modelo cargando o prompt truncado).")
        return content

    @staticmethod
    def is_available(host: str = "http://localhost:11434") -> bool:
        """Comprueba si el servidor de Ollama responde."""
        try:
            req = urllib.request.Request(f"{host.rstrip('/')}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False
