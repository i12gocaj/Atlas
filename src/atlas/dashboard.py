"""Exporta un unico data.json con todo lo que el dashboard necesita.

Consolida las señales deterministas (recalculadas al vuelo) con las salidas que
dependen del LLM (brief, sintesis de boilerplate) y las metricas de validacion,
que se leen de sus ficheros de cache en data/. Asi el dashboard es un front
estatico que no depende del modelo en directo: pre-generas una vez, y la demo es
100% fiable.

Si algun fichero de cache falta, esa seccion se omite con elegancia.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from . import validation as validation_mod
from .analysis import policy as policy_mod
from .analysis import scorecard as scorecard_mod
from .analysis import whatif as whatif_mod
from .signals import aggregations


def _load_json(path: Path) -> Any | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _records(df: pd.DataFrame, cols: list[str], n: int | None = None) -> list[dict]:
    view = df[cols]
    if n is not None:
        view = view.head(n)
    return json.loads(view.to_json(orient="records", force_ascii=False))


def build_dashboard_data(
    events_path: str | Path,
    data_dir: str | Path = "data",
    policy_path: str | Path = "policy.yaml",
) -> dict:
    """Construye el diccionario de datos del dashboard."""
    data_dir = Path(data_dir)
    df = aggregations.load_dataframe(events_path)
    signals = aggregations.compute_all_signals(df)
    summary = signals["summary"]

    # Cuadro de cumplimiento (determinista). Si falta la politica, se omite.
    policy_result = None
    ceilings = scorecard_mod.DEFAULT_CEILINGS
    token_threshold = scorecard_mod.WASTE_TOKEN_THRESHOLD
    if Path(policy_path).exists():
        policy_obj = policy_mod.load_policy(policy_path)
        policy_result = policy_mod.evaluate(df, policy_obj)
        reglas = policy_obj["reglas"]
        ceilings = reglas["techo_coste_semanal"]["techo_eur_por_criticidad"]
        token_threshold = int(reglas["sin_derroche_modelo"]["umbral_tokens"])

    # Salud de gobierno semana a semana (longitudinal, determinista).
    scorecard_result = scorecard_mod.weekly_scorecard(df, ceilings, token_threshold)

    # Tendencia semanal del equipo con anomalia (para el grafico del pico).
    anomalies = signals["cost_anomalies"]
    anomaly = _records(anomalies, list(anomalies.columns), 1)[0] if not anomalies.empty else None
    spike_team = anomaly["team"] if anomaly else signals["cost_by_team"].iloc[0]["team"]
    trend = signals["weekly_cost_trend"]
    spike_trend = _records(
        trend[trend["team"] == spike_team].assign(cost_eur=lambda d: d["cost_eur"].round(2)),
        ["iso_week", "cost_eur"],
    )

    # Pico de coste semanal por equipo: alimenta el simulador del techo (cliente),
    # que deja arrastrar el techo y ver que equipos lo superan. Determinista.
    peaks = (
        trend.groupby("team")["cost_eur"].max().round(2).reset_index()
        .rename(columns={"cost_eur": "peak_eur"})
        .sort_values("peak_eur", ascending=False)
    )
    team_peaks = _records(peaks, ["team", "peak_eur"])

    savings = signals["expensive_on_small_tasks"]
    savings_top = _records(savings, list(savings.columns), 1)[0] if not savings.empty else None

    # Ejemplo de secreto en lenguaje natural (el que la herramienta no caza).
    nl_secret = None
    pw = df[(df["gt_contains_secret"]) & (df["gt_secret_type"] == "password")]
    if not pw.empty:
        row = pw.iloc[0]
        nl_secret = {"team": row["team"], "user": row["user_id"], "text": row["prompt_text"]}

    # Salidas cacheadas (dependientes de LLM y validacion).
    brief = _load_json(data_dir / "brief.json")
    vsec = _load_json(data_dir / "validate_secrets.json")
    vint = _load_json(data_dir / "validate_intent.json")
    vpii = _load_json(data_dir / "validate_pii.json")

    evidence = {}
    if vsec:
        nl_n = vsec["lenguaje_natural"]["positivos"]
        nl_recall = vsec["lenguaje_natural"]["recall_llm"]
        ci = validation_mod.wilson_interval(round(nl_recall * nl_n), nl_n)
        evidence["secrets"] = {
            "tool_recall_nl": vsec["lenguaje_natural"]["recall_baseline"],
            "llm_recall_nl": nl_recall,
            "llm_ci": ci,
            "ci_n": nl_n,        # positivos en lenguaje natural (para el IC)
            "total_n": vsec["n"],  # total de casos etiquetados (para el pie)
        }
    if vint:
        n = vint["n"]
        acc = vint["llm_accuracy"]
        ci = validation_mod.wilson_interval(round(acc * n), n)
        evidence["intent"] = {
            "rule_acc": vint["rule_accuracy"],
            "llm_acc": acc,
            "llm_ci": ci,
            "rule_acc_en": vint["por_idioma"].get("en", {}).get("rule_accuracy"),
            "llm_acc_en": vint["por_idioma"].get("en", {}).get("llm_accuracy"),
            "n": n,
        }
    if vpii:
        evidence["pii"] = {
            "precision": vpii["herramienta"]["precision"],
            "recall": vpii["herramienta"]["recall"],
            "n": vpii["n"],
            "decoys_n": vpii["senuelos"]["n"],
            "decoys_fp": vpii["senuelos"]["falsos_positivos"],
        }

    # Coste de output que nadie acepto: la bolsa de gasto sin valor mas grande
    # (mayor que el ahorro por derroche). Determinista, suma directa.
    total_cost = float(summary["total_cost_eur"])
    rejected_cost = round(float(df[~df["accepted"]]["cost_eur"].sum()), 2)
    rejected_pct = round(rejected_cost / total_cost * 100, 1) if total_cost else 0.0

    return {
        "meta": {
            "events": summary["total_events"],
            "sessions": summary["total_sessions"],
            "weeks": summary["weeks"],
            "teams": summary["teams"],
            "users": summary["users"],
            "total_cost_eur": summary["total_cost_eur"],
            "rejected_cost_eur": rejected_cost,
            "rejected_pct": rejected_pct,
            "model": (brief or {}).get("_meta", {}).get("model", "qwen2.5:7b"),
        },
        "brief": brief,
        "policy": policy_result,
        "scorecard": scorecard_result,
        "cost_by_team": _records(
            signals["cost_by_team"].assign(cost_eur=lambda d: d["cost_eur"].round(2)),
            ["team", "cost_eur"],
        ),
        "acceptance_by_team": _records(signals["acceptance_by_team"], ["team", "acceptance_rate"]),
        "anomaly": anomaly,
        "spike_team": spike_team,
        "spike_trend": spike_trend,
        "team_peaks": team_peaks,
        "savings": savings_top,
        "whatif": whatif_mod.simulate_policy(df),
        "nl_secret": nl_secret,
        "evidence": evidence,
    }


def export(
    events_path: str | Path,
    out_path: str | Path,
    data_dir: str | Path = "data",
    policy_path: str | Path = "policy.yaml",
) -> dict:
    """Escribe el data.json (y un data.js global) del dashboard y devuelve el dict.

    data.js permite abrir el dashboard como fichero (file://) sin servidor ni
    fetch: el front solo lee window.ATLAS_DATA. Asi la demo es 100% offline.
    """
    data = build_dashboard_data(events_path, data_dir, policy_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    out.write_text(payload, encoding="utf-8")
    (out.parent / "data.js").write_text(f"window.ATLAS_DATA = {payload};\n", encoding="utf-8")
    return data
