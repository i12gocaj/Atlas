"""Scorecard de gobernanza continua (longitudinal, determinista).

Atlas no es una foto fija: es un sistema que corre cada semana. Este modulo
calcula un indice de salud de gobierno (0 a 100) por cada una de las 8 semanas,
descompuesto en cuatro dimensiones (seguridad, coste, eficiencia, adopcion), y
los deltas semana contra semana. Asi se ve la TENDENCIA: cuando un equipo se
sale de la politica, la salud cae, y queda claro en que semana intervenir.

Sin LLM: son las mismas reglas deterministas del motor de politicas, pero
medidas semana a semana en vez de sobre el agregado.
"""

from __future__ import annotations

import pandas as pd

from .. import config

# Techos de coste por criticidad. Misma referencia que policy.yaml; el dashboard
# pasa los de la politica cargada para no duplicar la fuente de verdad.
DEFAULT_CEILINGS = {"alta": 50, "media": 40, "baja": 30}

# Pesos de cada dimension en el indice global. La seguridad y el coste pesan mas
# porque son el riesgo de gobierno mas tangible; la adopcion es un suelo estable.
WEIGHTS = {"seguridad": 0.30, "coste": 0.30, "eficiencia": 0.25, "adopcion": 0.15}

WASTE_TOKEN_THRESHOLD = 700


def _team_criticality() -> dict[str, str]:
    return {t.name: t.criticality for t in config.TEAMS}


def _security(week: pd.DataFrame) -> tuple[float, int]:
    """100 si no hay fugas esa semana; cada secreto resta 25 puntos.

    Las fugas son las que el detector de Atlas recupera (baseline + LLM local);
    en el dataset coincide con gt_contains_secret, que usamos como su salida
    cacheada para que la dimension de seguridad sea determinista (ver el detalle
    en analysis/policy._check_secrets y el test que lo demuestra).
    """
    leaks = int(week["gt_contains_secret"].sum())
    return max(0.0, 100.0 - 25.0 * leaks), leaks


def _cost_discipline(week: pd.DataFrame, ceilings: dict[str, int]) -> tuple[float, int]:
    """Fraccion de equipos activos dentro de su techo semanal de coste."""
    crit = _team_criticality()
    by_team = week.groupby("team")["cost_eur"].sum()
    if by_team.empty:
        return 100.0, 0
    within = sum(1 for team, cost in by_team.items() if cost <= ceilings[crit[team]])
    over = len(by_team) - within
    return within / len(by_team) * 100.0, over


def _efficiency(week: pd.DataFrame, token_threshold: int = WASTE_TOKEN_THRESHOLD) -> tuple[float, float]:
    """100 menos la fraccion del gasto que es modelo caro en tareas triviales."""
    total = float(week["cost_eur"].sum())
    if total <= 0:
        return 100.0, 0.0
    cheap = config.MODELS[config.CHEAP_MODEL]
    small = week[(week["model_tier"] == "caro") & (week["total_tokens"] <= token_threshold)]
    if small.empty:
        return 100.0, 0.0
    cost_if_cheap = (
        small["input_tokens"] / 1000.0 * cheap.price_per_1k_input
        + small["output_tokens"] / 1000.0 * cheap.price_per_1k_output
    ).sum()
    waste = float(small["cost_eur"].sum() - cost_if_cheap)
    frac = max(0.0, waste / total)
    return max(0.0, min(100.0, 100.0 * (1 - frac))), round(waste, 2)


def _adoption(week: pd.DataFrame) -> tuple[float, float]:
    """Tasa de aceptacion a nivel sesion esa semana (mismo metodo que las senales)."""
    sessions = week.groupby("session_id")["accepted"].any()
    if sessions.empty:
        return 0.0, 0.0
    rate = float(sessions.mean())
    return rate * 100.0, round(rate, 3)


def weekly_scorecard(
    df: pd.DataFrame,
    ceilings: dict[str, int] | None = None,
    token_threshold: int = WASTE_TOKEN_THRESHOLD,
) -> dict:
    """Calcula el indice de salud de gobierno por semana y los deltas."""
    ceilings = ceilings or DEFAULT_CEILINGS
    weeks_out = []
    for iso_week in sorted(df["iso_week"].unique()):
        wk = df[df["iso_week"] == iso_week]
        sec, leaks = _security(wk)
        cost, teams_over = _cost_discipline(wk, ceilings)
        eff, waste = _efficiency(wk, token_threshold)
        adopt, acc_rate = _adoption(wk)
        # Redondeamos las dimensiones primero y el indice se calcula sobre ellas:
        # asi el numero mostrado es exactamente la media de los que se ven.
        seg_r, cost_r, eff_r, adopt_r = round(sec, 1), round(cost, 1), round(eff, 1), round(adopt, 1)
        score = (
            WEIGHTS["seguridad"] * seg_r
            + WEIGHTS["coste"] * cost_r
            + WEIGHTS["eficiencia"] * eff_r
            + WEIGHTS["adopcion"] * adopt_r
        )
        weeks_out.append(
            {
                "iso_week": iso_week,
                "score": round(score, 1),
                "seguridad": seg_r,
                "coste": cost_r,
                "eficiencia": eff_r,
                "adopcion": adopt_r,
                "fugas": leaks,
                "equipos_sobre_techo": teams_over,
                "derroche_eur": waste,
                "aceptacion": acc_rate,
            }
        )

    # df sin semanas (vacio): estructura neutra, no reventar con IndexError.
    if not weeks_out:
        return {
            "weeks": [],
            "latest": None,
            "delta_vs_prev": 0.0,
            "delta_vs_inicio": 0.0,
            "pico": None,
            "pesos": WEIGHTS,
        }

    latest = weeks_out[-1]
    first = weeks_out[0]
    prev = weeks_out[-2] if len(weeks_out) >= 2 else first
    best = max(weeks_out, key=lambda w: w["score"])

    return {
        "weeks": weeks_out,
        "latest": latest,
        "delta_vs_prev": round(latest["score"] - prev["score"], 1),
        "delta_vs_inicio": round(latest["score"] - first["score"], 1),
        "pico": {"iso_week": best["iso_week"], "score": best["score"]},
        "pesos": WEIGHTS,
    }
