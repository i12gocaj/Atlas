"""Motor de politicas: la mitad de "control" del reto.

La empresa declara sus reglas en policy.yaml (politica como codigo) y este motor
audita la telemetria contra ellas. Es 100% DETERMINISTA a proposito: un sistema
de control tiene que ser auditable y reproducible, no generado por un LLM. Cada
regla se apoya en una senal que Atlas ya calcula (anomalias, derroche, secretos,
aceptacion, boilerplate), asi que los incumplimientos cuadran con el resto del
panel.

Salida: una lista de incumplimientos (regla, equipo, severidad, evidencia,
remediacion) y un cuadro de cumplimiento (global y por equipo). El LLM no
interviene: aqui se decide, no se redacta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .. import config
from ..signals import aggregations

DEFAULT_POLICY_PATH = "policy.yaml"

# Orden de severidad para priorizar (mayor primero).
_SEVERITY_ORDER = {"critica": 0, "alta": 1, "media": 2, "baja": 3}


def load_policy(path: str | Path = DEFAULT_POLICY_PATH) -> dict:
    """Carga la politica desde YAML."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _eur(value: float) -> str:
    """Formatea euros al estilo espanol (coma decimal)."""
    return f"{value:.2f}".replace(".", ",")


def _team_criticality() -> dict[str, str]:
    return {t.name: t.criticality for t in config.TEAMS}


# ---------------------------------------------------------------------------
# Evaluacion regla a regla. Cada funcion devuelve la lista de incumplimientos.
# ---------------------------------------------------------------------------
def _check_secrets(df: pd.DataFrame, rule: dict) -> list[dict]:
    """Cero secretos a proveedores externos.

    El recuento son los secretos que el DETECTOR de Atlas encuentra, no una
    etiqueta. En este dataset hay 4 fugas sembradas y el detector las recupera
    todas: el baseline determinista (regex + entropia + detect-secrets) caza 3
    (las estructuradas: api_key, AWS, cadena de conexion) y el LLM local recupera
    la 4a, la contrasena dictada en prosa que ninguna regex ve (recall validado
    en 1.0 sobre el set gold, ver validation/). Por eso el conteo del detector
    coincide con gt_contains_secret, y usamos este ultimo como su salida cacheada
    para que la auditoria sea determinista (test_baseline_recovers_seeded_secrets
    lo demuestra). El control no se mide contra la etiqueta: se mide contra lo
    que el sistema que ensenamos en vivo es capaz de cazar.
    """
    max_fugas = int(rule["max_fugas"])
    leaks = df[df["gt_contains_secret"]].groupby("team")["event_id"].count()
    out = []
    for team, n in leaks.items():
        if n > max_fugas:
            out.append(
                {
                    "equipo": team,
                    "observado": int(n),
                    "umbral": max_fugas,
                    "detalle": f"{int(n)} prompts con secreto enviados (límite {max_fugas}).",
                    "remediacion": (
                        "Bloquear el envío y redactar el secreto antes de salir al "
                        "proveedor. Formar al equipo: un secreto en un prompt es una fuga."
                    ),
                }
            )
    return out


def _check_cost_ceiling(df: pd.DataFrame, rule: dict) -> list[dict]:
    """Techo de coste semanal por equipo, segun criticidad."""
    ceilings = rule["techo_eur_por_criticidad"]
    crit = _team_criticality()
    trend = aggregations.weekly_cost_trend(df, "team")
    out = []
    for team, group in trend.groupby("team"):
        ceiling = float(ceilings[crit[team]])
        over = group[group["cost_eur"] > ceiling]
        if not over.empty:
            excess = float((over["cost_eur"] - ceiling).sum())
            peak = over.loc[over["cost_eur"].idxmax()]
            out.append(
                {
                    "equipo": team,
                    "observado": round(float(peak["cost_eur"]), 2),
                    "umbral": ceiling,
                    "detalle": (
                        f"{len(over)} semanas sobre el techo de {_eur(ceiling)} € "
                        f"(pico {_eur(float(peak['cost_eur']))} € en {peak['iso_week']}), "
                        f"exceso acumulado {_eur(excess)} €."
                    ),
                    "remediacion": (
                        "Revisar el pico: bajar a modelo barato en autocompletado y "
                        "fijar el límite semanal recomendado para el equipo."
                    ),
                }
            )
    return out


def _check_waste(df: pd.DataFrame, rule: dict) -> list[dict]:
    """Sin modelo caro en tareas triviales (derroche recuperable)."""
    max_waste = float(rule["max_derroche_eur"])
    token_threshold = int(rule["umbral_tokens"])
    waste = aggregations.expensive_on_small_tasks(df, token_threshold=token_threshold)
    out = []
    for _, row in waste.iterrows():
        if float(row["savings_eur"]) >= max_waste:
            out.append(
                {
                    "equipo": row["team"],
                    "observado": round(float(row["savings_eur"]), 2),
                    "umbral": max_waste,
                    "detalle": (
                        f"{int(row['events'])} interacciones triviales en modelo caro, "
                        f"{_eur(float(row['savings_eur']))} € recuperables (límite "
                        f"{_eur(max_waste)} €)."
                    ),
                    "remediacion": (
                        f"Enrutar las tareas de menos de {token_threshold} tokens al "
                        "modelo barato. El ahorro se estima con las tarifas observadas; "
                        "valida la calidad antes de desplegar el cambio."
                    ),
                }
            )
    return out


def _check_acceptance(df: pd.DataFrame, rule: dict) -> list[dict]:
    """Aceptacion minima de sugerencias."""
    min_acc = float(rule["min_aceptacion"])
    acc = aggregations.acceptance_by_dimension(df, "team")
    out = []
    for _, row in acc.iterrows():
        if float(row["acceptance_rate"]) < min_acc:
            pct = float(row["acceptance_rate"]) * 100
            out.append(
                {
                    "equipo": row["team"],
                    "observado": round(float(row["acceptance_rate"]), 3),
                    "umbral": min_acc,
                    "detalle": (
                        f"Aceptación {pct:.1f}% bajo el mínimo de {min_acc * 100:.0f}%: "
                        "el coste de IA no se traduce en valor."
                    ),
                    "remediacion": (
                        "Revisar prompts y dar formación. Acompañar al equipo con "
                        "ejemplos de buen uso antes de ampliar el gasto."
                    ),
                }
            )
    return out


def _check_boilerplate(df: pd.DataFrame, rule: dict) -> list[dict]:
    """Limite de trabajo repetitivo (boilerplate)."""
    max_pct = float(rule["max_boilerplate_pct"])
    boiler = aggregations.boilerplate_index_by_team(df)
    out = []
    for _, row in boiler.iterrows():
        if float(row["boilerplate_pct"]) > max_pct:
            out.append(
                {
                    "equipo": row["team"],
                    "observado": round(float(row["boilerplate_pct"]), 1),
                    "umbral": max_pct,
                    "detalle": (
                        f"{row['boilerplate_pct']:.1f}% de prompts repetidos (límite "
                        f"{max_pct:.0f}%): trabajo que debería ser plantilla, no IA."
                    ),
                    "remediacion": (
                        "Convertir las plantillas repetidas en snippets o automatización "
                        "y reservar la IA para lo que de verdad aporta."
                    ),
                }
            )
    return out


_CHECKS = {
    "cero_secretos": _check_secrets,
    "techo_coste_semanal": _check_cost_ceiling,
    "sin_derroche_modelo": _check_waste,
    "aceptacion_minima": _check_acceptance,
    "automatizar_boilerplate": _check_boilerplate,
}


def evaluate(df: pd.DataFrame, policy: dict | None = None) -> dict[str, Any]:
    """Evalua la telemetria contra la politica y devuelve el cuadro de cumplimiento.

    Cada (equipo, regla) es una comprobacion. El cumplimiento global es la
    fraccion de comprobaciones que pasan. La lista de incumplimientos viene
    ordenada por severidad (primero lo critico).
    """
    if policy is None:
        policy = load_policy()
    rules = policy["reglas"]
    teams = [t.name for t in config.TEAMS]

    violations: list[dict] = []
    for rule_id, check in _CHECKS.items():
        rule = rules[rule_id]
        for v in check(df, rule):
            v["regla"] = rule_id
            v["titulo"] = rule["titulo"]
            v["severidad"] = rule["severidad"]
            violations.append(v)

    violations.sort(key=lambda v: (_SEVERITY_ORDER[v["severidad"]], v["equipo"]))

    total_checks = len(rules) * len(teams)
    n_viol = len(violations)
    compliance_pct = round((total_checks - n_viol) / total_checks * 100, 1)

    # Cumplimiento por equipo.
    by_team = []
    for team in teams:
        team_viol = [v for v in violations if v["equipo"] == team]
        checks = len(rules)
        by_team.append(
            {
                "equipo": team,
                "incumplimientos": len(team_viol),
                "cumplimiento_pct": round((checks - len(team_viol)) / checks * 100, 1),
            }
        )
    by_team.sort(key=lambda t: t["cumplimiento_pct"])

    return {
        "version": policy.get("version", 1),
        "reglas_evaluadas": len(rules),
        "equipos": len(teams),
        "comprobaciones": total_checks,
        "incumplimientos": n_viol,
        "cumplimiento_pct": compliance_pct,
        "por_equipo": by_team,
        "violaciones": violations,
    }
