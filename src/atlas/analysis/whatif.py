"""Simulador what-if (contrafactual): cierra el eslabon Decisiones.

Pasa de "te recomiendo bajar" a "bajar te ahorra X". Reproyecta el coste real de
las semanas observadas bajo la POLITICA recomendada (redirigir el modelo caro al
barato en las tareas pequenas, que es justo el ahorro que detectamos) y compara
antes/despues, por semana y en total, anualizando con un intervalo honesto.

Es 100% DETERMINISTA: no interviene ningun LLM en las cifras. La unica
recomendacion que aplica es la que ya esta validada (modelo caro en tareas
pequenas), asi que el ahorro contrafactual cuadra al centimo con la señal de
ahorro del brief.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from ..signals import aggregations

# Fraccion del ahorro teorico que se considera realmente recuperable (intervalo
# conservador-optimista): no todo se captura en la practica.
RECOVERY_LOW = 0.60
RECOVERY_HIGH = 1.00
WEEKS_PER_YEAR = 52


def simulate_policy(df: pd.DataFrame, token_threshold: int = 700) -> dict:
    """Reproyecta el coste bajo la politica 'modelo barato en tareas pequenas'."""
    cheap = config.MODELS[config.CHEAP_MODEL]
    sim = df.copy()
    sim["cf_cost"] = sim["cost_eur"]

    # Aplicamos la politica solo a los equipos con una oportunidad de ahorro REAL
    # (los mismos que reporta expensive_on_small_tasks, con su filtro de eventos
    # minimos), para que el ahorro contrafactual cuadre con la señal del brief.
    qualifying = set(aggregations.expensive_on_small_tasks(df, token_threshold)["team"])

    # Candidatos: modelo caro en interacciones pequenas (la oportunidad de ahorro).
    mask = (
        (sim["model_tier"] == "caro")
        & (sim["total_tokens"] <= token_threshold)
        & (sim["team"].isin(qualifying))
    )
    sim.loc[mask, "cf_cost"] = (
        sim.loc[mask, "input_tokens"] / 1000.0 * cheap.price_per_1k_input
        + sim.loc[mask, "output_tokens"] / 1000.0 * cheap.price_per_1k_output
    )

    actual_total = float(sim["cost_eur"].sum())
    cf_total = float(sim["cf_cost"].sum())
    saved = round(actual_total - cf_total, 2)
    weeks = int(sim["iso_week"].nunique())

    # Equipo con mas ahorro (donde se concentra la decision).
    by_team = sim[mask].assign(saved=lambda d: d["cost_eur"] - d["cf_cost"]).groupby("team")["saved"].sum()
    spike_team = by_team.idxmax() if not by_team.empty else sim.groupby("team")["cost_eur"].sum().idxmax()

    # Serie semanal del equipo: coste real vs contrafactual (la curva del pico
    # baja bajo la politica).
    team_df = sim[sim["team"] == spike_team]
    weekly = (
        team_df.groupby("iso_week")
        .agg(actual=("cost_eur", "sum"), counterfactual=("cf_cost", "sum"))
        .reset_index()
        .sort_values("iso_week")
    )
    weekly_records = [
        {"iso_week": r["iso_week"], "actual": round(r["actual"], 2), "counterfactual": round(r["counterfactual"], 2)}
        for _, r in weekly.iterrows()
    ]

    annual = saved * WEEKS_PER_YEAR / weeks if weeks else 0.0
    return {
        "spike_team": spike_team,
        "weeks": weeks,
        "actual_total_eur": round(actual_total, 2),
        "counterfactual_total_eur": round(cf_total, 2),
        "saved_eur": saved,
        "saved_annual_low_eur": round(annual * RECOVERY_LOW, 0),
        "saved_annual_high_eur": round(annual * RECOVERY_HIGH, 0),
        "weekly": weekly_records,
    }
