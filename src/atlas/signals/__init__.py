"""Capa de señales deterministas de Atlas.

Convierte el flujo crudo de eventos en metricas agregadas por usuario, equipo,
proyecto y semana. Es DETERMINISTA y SIN IA a proposito: estas son las cifras
duras (coste, tokens, ratios, tendencias) que el agente de la Semana 2 cita pero
nunca inventa. Mantener esta frontera es la base de la honestidad de la demo.
"""

from .aggregations import compute_all_signals, load_dataframe  # noqa: F401
