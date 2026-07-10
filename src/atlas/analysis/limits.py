"""Logica DETERMINISTA de recomendacion de limites por equipo.

Centralizada aqui para que el brief y el artefacto usen exactamente la misma
regla, consciente del derroche. La decision (subir/mantener/bajar/optimizar) NO
la toma el LLM: es una funcion pura de las señales. El LLM, como mucho, redacta
el motivo en prosa, nunca cambia la accion.
"""

from __future__ import annotations

import pandas as pd

# Ahorro semanal a partir del cual se pide optimizar antes de tocar el limite.
SAVINGS_SIGNIFICANT_EUR = 1.0


def decide_action(row: pd.Series) -> tuple[str, str]:
    """Decide (accion, motivo) para un equipo a partir de sus señales de limite.

    Reglas, en orden de prioridad:
    1. Anomalia activa: bajar (optimizar antes de fijar el limite).
    2. Ahorro recuperable significativo: optimizar.
    3. Limite recomendado claramente por encima del gasto: subir (con margen).
    4. Limite recomendado claramente por debajo del gasto: bajar.
    5. En equilibrio: mantener.
    """
    if bool(row["has_anomaly"]):
        return "bajar", "Anomalía de coste activa. Optimizar el modelo antes de fijar el límite."
    if float(row["avg_weekly_savings"]) >= SAVINGS_SIGNIFICANT_EUR:
        return "optimizar", "Ahorro recuperable usando un modelo más barato en tareas pequeñas."
    if float(row["recommended_weekly_limit_eur"]) > float(row["avg_weekly_cost"]) * 1.05:
        return "subir", "Uso eficiente y criticidad que justifican algo de margen."
    if float(row["recommended_weekly_limit_eur"]) < float(row["avg_weekly_cost"]) * 0.95:
        return "bajar", "Gasto por encima del nivel eficiente recomendado."
    return "mantener", "Gasto alineado con el nivel eficiente recomendado."


def build_recommendations(limits: pd.DataFrame) -> list[dict]:
    """Recomendaciones de limite por equipo, deterministas (sin LLM)."""
    out = []
    for _, row in limits.iterrows():
        action, motivo = decide_action(row)
        out.append({"equipo": row["team"], "accion": action, "motivo": motivo})
    return out
