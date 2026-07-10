"""Configuracion de la capa LLM y carga de variables de entorno.

Diseno: Atlas funciona 100% en LOCAL (Ollama). Es una decision de producto, no
solo tecnica: Atlas analiza prompts que pueden contener secretos y PII, asi que
lo correcto es procesarlos en la maquina, sin mandarlos a ninguna API de
terceros. Ademas no depende de la red en la demo, es gratis y reproducible. No
hay backend en la nube ni API keys: el detector de fugas no filtra, a su vez, los
datos a un tercero.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Nombres de variables de entorno.
ENV_OLLAMA_MODEL = "ATLAS_OLLAMA_MODEL"
ENV_OLLAMA_HOST = "ATLAS_OLLAMA_HOST"

# Valores por defecto.
# qwen2.5:7b elegido por benchmark (scripts/benchmark_models.py): misma calidad
# que phi4:14b en lo critico (deteccion de secretos, caza la contrasena en
# lenguaje natural) pero ~2x mas rapido y la mitad de tamano en el benchmark
# local de scripts/benchmark_models.py.
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def load_dotenv(path: str | Path = ".env") -> None:
    """Carga un fichero .env en os.environ (sin sobrescribir lo ya definido).

    Loader minimo y sin dependencias: lineas KEY=VALOR, ignora comentarios y
    lineas vacias. No interpreta comillas complejas, solo recorta las simples.
    """
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class LLMSettings:
    """Ajustes resueltos de la capa LLM (solo local)."""

    ollama_model: str
    ollama_host: str


def load_settings(dotenv_path: str | Path = ".env") -> LLMSettings:
    """Resuelve los ajustes de LLM desde entorno (cargando .env si existe)."""
    load_dotenv(dotenv_path)
    return LLMSettings(
        ollama_model=os.environ.get(ENV_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL),
        ollama_host=os.environ.get(ENV_OLLAMA_HOST, DEFAULT_OLLAMA_HOST),
    )
