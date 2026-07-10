"""Atlas: observabilidad y gobierno del uso de IA en desarrollo.

Reto 4 del Hackathon Catedra Atmira. La Semana 1 cubre la base de datos (dataset
sintetico reproducible), la capa de señales deterministas y la deteccion baseline
de secretos. El agente analista LLM y el dashboard llegan en la Semana 2.

Capas (de dato crudo a decision):
- generation: produce el dataset sintetico de eventos de uso de IA.
- signals: agrega los eventos en metricas deterministas (coste, mix, ratios).
- detection: baseline de secretos (regex mas entropia) para el contraste con IA.
- storage: persistencia JSONL/CSV.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .generation.generator import generate_events  # noqa: F401
from .schema import AIUsageEvent  # noqa: F401
