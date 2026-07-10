"""Esquema canonico del evento de uso de IA (AIUsageEvent).

Un evento representa UNA interaccion de un desarrollador con un asistente de IA:
un prompt enviado y su respuesta. Es la unidad atomica de toda la telemetria
que Atlas observa.

Diseno clave: separamos dos tipos de campos.

- OBSERVABLES: lo que un sistema de telemetria real captaria (quien, cuando,
  que modelo, cuantos tokens, coste, el texto del prompt y de la respuesta, si
  se acepto la sugerencia, si fue un reintento).
- GROUND TRUTH (prefijo `gt_`): etiquetas ocultas que SOLO existen porque el
  dataset es sintetico y nosotros las plantamos. Sirven para validar de forma
  honesta los clasificadores de la Semana 2 (categoria de tarea por LLM,
  deteccion de secretos, boilerplate). En produccion estos campos no existirian.

Mantener esta frontera explicita es lo que nos permite demostrar al jurado, sin
trampa, cuanto acierta la IA frente a una baseline de reglas.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from . import config

SCHEMA_VERSION = "1.0.0"


@dataclass
class AIUsageEvent:
    """Una interaccion de un desarrollador con un asistente de IA."""

    # --- Identidad y contexto (observable) ---
    event_id: str
    session_id: str
    timestamp: str  # ISO 8601, p.ej. "2026-04-06T09:30:00"
    user_id: str
    team: str
    project: str
    criticality: str  # alta | media | baja

    # --- Que herramienta y modelo (observable) ---
    assistant: str  # nombre del asistente (p.ej. "ide-copilot")
    model: str  # clave en config.MODELS

    # --- Consumo y coste (observable, determinista) ---
    input_tokens: int
    output_tokens: int
    cost_eur: float
    latency_ms: int

    # --- Contenido (observable) ---
    prompt_text: str
    response_summary: str

    # --- Resultado e hilo (observable) ---
    accepted: bool
    is_retry: bool
    retry_of: Optional[str]  # event_id del primer intento de la sesion, o None

    # --- Ground truth (oculto, prefijo gt_) ---
    gt_task_category: str  # categoria real de la tarea
    gt_contains_secret: bool  # si el prompt lleva un secreto plantado
    gt_secret_type: Optional[str]  # tipo de secreto (connection_string, password, api_key) o None
    gt_is_boilerplate: bool  # si el prompt pertenece al cluster de boilerplate
    gt_scenario: Optional[str]  # etiqueta del escenario sembrado, o None

    # --- Metadatos ---
    schema_version: str = field(default=SCHEMA_VERSION)

    # ------------------------------------------------------------------
    # Validacion
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        """Valida invariantes basicas. Falla pronto y claro si algo no cuadra."""
        if self.model not in config.MODELS:
            raise ValueError(f"Modelo desconocido: {self.model!r}")
        if self.criticality not in config.CRITICALITY_LEVELS:
            raise ValueError(f"Criticidad invalida: {self.criticality!r}")
        if self.gt_task_category not in config.TASK_CATEGORIES:
            raise ValueError(f"Categoria de tarea invalida: {self.gt_task_category!r}")
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Los tokens no pueden ser negativos")
        if self.cost_eur < 0:
            raise ValueError("El coste no puede ser negativo")
        if self.is_retry and self.retry_of is None:
            raise ValueError("Un reintento debe apuntar a retry_of")
        if not self.is_retry and self.retry_of is not None:
            raise ValueError("Un primer intento no puede tener retry_of")
        if self.gt_contains_secret and self.gt_secret_type is None:
            raise ValueError("Un evento con secreto debe indicar gt_secret_type")

    # ------------------------------------------------------------------
    # Serializacion
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Devuelve el evento como diccionario plano (apto para JSON o pandas)."""
        return asdict(self)

    def to_json_line(self) -> str:
        """Serializa el evento a una linea JSON (formato JSONL)."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AIUsageEvent":
        """Reconstruye un evento desde un diccionario (ignora claves extra)."""
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)


# Columnas observables, utiles para construir vistas que simulen "lo que el
# sistema realmente ve" (sin las etiquetas gt_).
OBSERVABLE_FIELDS: tuple[str, ...] = (
    "event_id",
    "session_id",
    "timestamp",
    "user_id",
    "team",
    "project",
    "criticality",
    "assistant",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_eur",
    "latency_ms",
    "prompt_text",
    "response_summary",
    "accepted",
    "is_retry",
    "retry_of",
)

GROUND_TRUTH_FIELDS: tuple[str, ...] = (
    "gt_task_category",
    "gt_contains_secret",
    "gt_secret_type",
    "gt_is_boilerplate",
    "gt_scenario",
)


def compute_cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calcula el coste en EUR de forma determinista a partir de tokens y tarifa.

    Esta funcion es deliberadamente SIN IA. El coste es una cifra dura y fiable
    que el agente luego cita pero nunca inventa.
    """
    tariff = config.MODELS[model]
    cost = (
        (input_tokens / 1000.0) * tariff.price_per_1k_input
        + (output_tokens / 1000.0) * tariff.price_per_1k_output
    )
    return round(cost, 4)
