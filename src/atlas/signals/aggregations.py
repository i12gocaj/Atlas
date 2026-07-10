"""Agregaciones deterministas sobre los eventos de uso de IA.

Cada funcion devuelve un DataFrame autocontenido y documentado. `compute_all_signals`
las orquesta y devuelve un diccionario listo para alimentar el dashboard o, en la
Semana 2, el contexto del agente analista.

Principio: aqui no se usa IA. Solo agregacion y reglas aritmeticas claras. Lo
unico que toca ground truth (gt_) es el indice de boilerplate, que en la Semana 1
es un placeholder a la espera del analisis semantico; queda marcado como tal.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .. import config
from ..storage import read_events_raw

# Umbral por defecto para marcar una anomalia de coste semana contra semana.
DEFAULT_ANOMALY_RATIO = 2.5
# Piso absoluto: no marcar anomalia si el coste de la semana es trivial (evita
# falsos avisos por ruido en equipos de gasto bajo).
ANOMALY_MIN_COST_EUR = 5.0
# Numero minimo de prompts en una sesion para considerarla "cadena de reintentos".
RETRY_CHAIN_MIN = 3


# ---------------------------------------------------------------------------
# Carga y enriquecimiento
# ---------------------------------------------------------------------------
def load_dataframe(path: str | Path) -> pd.DataFrame:
    """Carga los eventos JSONL en un DataFrame con columnas derivadas."""
    df = pd.DataFrame(read_events_raw(path))
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["iso_week"] = df["timestamp"].dt.strftime("%G-W%V")
    df["total_tokens"] = df["input_tokens"] + df["output_tokens"]
    df["model_tier"] = df["model"].map(lambda m: config.MODELS[m].tier)
    return df


def _session_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Resume el dataset a nivel de sesion (una tarea = una fila)."""
    grouped = df.groupby("session_id")
    sessions = grouped.agg(
        user_id=("user_id", "first"),
        team=("team", "first"),
        project=("project", "first"),
        iso_week=("iso_week", "first"),
        prompts=("event_id", "count"),
        accepted=("accepted", "any"),
        cost_eur=("cost_eur", "sum"),
    ).reset_index()
    sessions["is_retry_chain"] = sessions["prompts"] >= RETRY_CHAIN_MIN
    return sessions


# ---------------------------------------------------------------------------
# Coste
# ---------------------------------------------------------------------------
def cost_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Coste, eventos y eficiencia agregados por una dimension (team/user/project)."""
    out = (
        df.groupby(dimension)
        .agg(
            cost_eur=("cost_eur", "sum"),
            events=("event_id", "count"),
            input_tokens=("input_tokens", "sum"),
            output_tokens=("output_tokens", "sum"),
        )
        .reset_index()
    )
    out["cost_per_event"] = (out["cost_eur"] / out["events"]).round(4)
    out["tokens_per_event"] = ((out["input_tokens"] + out["output_tokens"]) / out["events"]).round(1)
    return out.sort_values("cost_eur", ascending=False).reset_index(drop=True)


def cost_by_model(df: pd.DataFrame) -> pd.DataFrame:
    """Coste y volumen por modelo, con su tier (barato/medio/caro)."""
    out = (
        df.groupby(["model", "model_tier"])
        .agg(cost_eur=("cost_eur", "sum"), events=("event_id", "count"))
        .reset_index()
    )
    return out.sort_values("cost_eur", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Mix de tareas
# ---------------------------------------------------------------------------
def task_mix_by_team(df: pd.DataFrame, category_field: str = "gt_task_category") -> pd.DataFrame:
    """Reparto de uso entre categorias de tarea, por equipo (en %).

    En la Semana 1 usamos la categoria real (gt_task_category) como aproximacion.
    En la Semana 2, pasar aqui la columna de categoria predicha por el LLM para
    reflejar lo que el sistema realmente ve.
    """
    counts = df.groupby(["team", category_field]).size().reset_index(name="events")
    totals = counts.groupby("team")["events"].transform("sum")
    counts["pct"] = (counts["events"] / totals * 100).round(1)
    return counts.sort_values(["team", "pct"], ascending=[True, False]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Aceptacion y reintentos (proxies de productividad y calidad de uso)
# ---------------------------------------------------------------------------
def acceptance_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Ratio de aceptacion a nivel de sesion, por dimension."""
    sessions = _session_frame(df)
    out = (
        sessions.groupby(dimension)
        .agg(sessions=("session_id", "count"), accepted=("accepted", "sum"))
        .reset_index()
    )
    out["acceptance_rate"] = (out["accepted"] / out["sessions"]).round(3)
    return out.sort_values("acceptance_rate", ascending=False).reset_index(drop=True)


def retry_rate_by_dimension(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Porcentaje de sesiones que fueron cadenas de reintentos (3 o mas prompts)."""
    sessions = _session_frame(df)
    out = (
        sessions.groupby(dimension)
        .agg(sessions=("session_id", "count"), retry_chains=("is_retry_chain", "sum"))
        .reset_index()
    )
    out["retry_chain_rate"] = (out["retry_chains"] / out["sessions"]).round(3)
    return out.sort_values("retry_chain_rate", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Tendencias y anomalias de coste
# ---------------------------------------------------------------------------
def weekly_cost_trend(df: pd.DataFrame, dimension: str = "team") -> pd.DataFrame:
    """Coste por semana y por dimension (formato largo: dimension, iso_week, coste)."""
    out = (
        df.groupby([dimension, "iso_week"])
        .agg(cost_eur=("cost_eur", "sum"), events=("event_id", "count"))
        .reset_index()
        .sort_values([dimension, "iso_week"])
        .reset_index(drop=True)
    )
    return out


def cost_anomalies(
    df: pd.DataFrame,
    ratio_threshold: float = DEFAULT_ANOMALY_RATIO,
    min_cost_eur: float = ANOMALY_MIN_COST_EUR,
) -> pd.DataFrame:
    """Detecta saltos de coste semana contra semana por equipo.

    Marca anomalia cuando el coste de una semana supera al de la anterior por
    encima de `ratio_threshold` y ademas esta por encima de un piso absoluto en
    euros (para no avisar por ruido en gasto trivial). Es una regla determinista:
    la EXPLICACION de la causa la aporta el agente.

    Nota de diseno (investigacion de herramientas): se evaluo el z-score robusto
    con MAD, recomendado para deteccion de outliers. No se adopto porque NO encaja
    nuestro caso: el pico de coste es un escalon SOSTENIDO (varias semanas), asi
    que pasa a ser la mayoria de la serie; la mediana se desplaza al nivel alto y
    el MAD marcaria como anomalas las semanas NORMALES. El ratio semana contra
    semana detecta el salto, que es justo la senal de gobierno que queremos, y es
    mas explicable. MAD seria correcto para outliers puntuales sobre una base
    estable, no para un cambio de regimen como este.
    """
    trend = weekly_cost_trend(df, "team")
    trend = trend.sort_values(["team", "iso_week"]).copy()
    trend["prev_cost"] = trend.groupby("team")["cost_eur"].shift(1)
    trend["wow_ratio"] = (trend["cost_eur"] / trend["prev_cost"]).round(2)
    flagged = (trend["wow_ratio"] >= ratio_threshold) & (trend["cost_eur"] >= min_cost_eur)
    anomalies = trend[flagged].copy()
    anomalies = anomalies[["team", "iso_week", "prev_cost", "cost_eur", "wow_ratio"]]
    return anomalies.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Oportunidad de ahorro: modelo caro en tareas pequenas
# ---------------------------------------------------------------------------
def expensive_on_small_tasks(
    df: pd.DataFrame, token_threshold: int = 700, min_events: int = 5
) -> pd.DataFrame:
    """Identifica uso del modelo caro en interacciones pequenas (candidatas a ahorro).

    Heuristica OBSERVABLE (no usa ground truth): modelo de tier caro con pocos
    tokens totales. Estima el ahorro si esas interacciones se hubieran resuelto
    con el modelo barato. Es la base cuantificada de la recomendacion de coste.
    """
    cheap = config.MODELS[config.CHEAP_MODEL]
    expensive_tiers = {"caro"}
    candidates = df[(df["model_tier"].isin(expensive_tiers)) & (df["total_tokens"] <= token_threshold)].copy()
    if candidates.empty:
        return pd.DataFrame(
            columns=["team", "events", "cost_eur", "cost_if_cheap", "savings_eur"]
        )
    candidates["cost_if_cheap"] = (
        candidates["input_tokens"] / 1000.0 * cheap.price_per_1k_input
        + candidates["output_tokens"] / 1000.0 * cheap.price_per_1k_output
    )
    out = (
        candidates.groupby("team")
        .agg(
            events=("event_id", "count"),
            cost_eur=("cost_eur", "sum"),
            cost_if_cheap=("cost_if_cheap", "sum"),
        )
        .reset_index()
    )
    # Descartamos equipos con muy pocas interacciones: una oportunidad de ahorro
    # de 1 o 2 eventos es ruido, no algo accionable (y descuadraba el total).
    out = out[out["events"] >= min_events]
    out["savings_eur"] = (out["cost_eur"] - out["cost_if_cheap"]).round(2)
    out["cost_eur"] = out["cost_eur"].round(2)
    out["cost_if_cheap"] = out["cost_if_cheap"].round(2)
    return out.sort_values("savings_eur", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Indice de boilerplate (placeholder Semana 1, semantico en Semana 2)
# ---------------------------------------------------------------------------
def boilerplate_index_by_team(df: pd.DataFrame) -> pd.DataFrame:
    """Fraccion de PRIMEROS INTENTOS que son boilerplate repetido, por equipo.

    Mide sobre primeros intentos (no reintentos), igual que el detector semantico
    de boilerplate (analysis/boilerplate.py): el boilerplate es la peticion inicial
    repetida, no los follow-ups de reintento. Asi esta cifra cuadra con la del
    detector y con el ground truth.

    Es una cifra de referencia (placeholder): el valor real lo da el clustering
    semantico del LLM, que detecta el boilerplate leyendo el texto sin etiquetas.
    """
    first = df[~df["is_retry"]]
    out = (
        first.groupby("team")
        .agg(events=("event_id", "count"), boilerplate=("gt_is_boilerplate", "sum"))
        .reset_index()
    )
    out["boilerplate_pct"] = (out["boilerplate"] / out["events"] * 100).round(1)
    return out.sort_values("boilerplate_pct", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Limite recomendado por equipo (heuristica placeholder)
# ---------------------------------------------------------------------------
# Holgura sobre el coste eficiente segun criticidad. A mayor criticidad, mas
# margen sobre el gasto eficiente. Nunca por debajo de 1.0: recortar el limite de
# un equipo que ya esta en su nivel eficiente (sin derroche) daria una accion
# "bajar" con un motivo falso. La presion de eficiencia viene del ahorro real
# detectado, no de un recorte arbitrario por criticidad.
_CRITICALITY_HEADROOM = {"alta": 1.30, "media": 1.10, "baja": 1.00}


def recommended_weekly_limits(
    df: pd.DataFrame, anomaly_ratio: float = DEFAULT_ANOMALY_RATIO
) -> pd.DataFrame:
    """Propone un limite semanal de coste por equipo, CONSCIENTE DEL DERROCHE.

    Clave: el limite se basa en el coste EFICIENTE (gasto medio menos el ahorro
    recuperable que el equipo esta tirando en modelo caro para tareas pequenas),
    no en el gasto actual inflado. Asi un equipo que derrocha no recibe mas
    presupuesto por su criticidad: primero se le pide optimizar.

    Esta capa solo da FACTOS (coste actual, ahorro, coste eficiente, si tiene
    anomalia). La decision final (subir/mantener/bajar/optimizar) la toma el
    agente, que reconcilia estos numeros. Aqui no emitimos el verbo a proposito.
    """
    num_weeks = max(int(df["iso_week"].nunique()), 1)
    trend = weekly_cost_trend(df, "team")
    avg = trend.groupby("team")["cost_eur"].mean().reset_index(name="avg_weekly_cost")
    crit = df.groupby("team")["criticality"].first().reset_index()

    savings = expensive_on_small_tasks(df)[["team", "savings_eur"]]
    anomaly_teams = set(cost_anomalies(df, anomaly_ratio)["team"])

    out = avg.merge(crit, on="team").merge(savings, on="team", how="left")
    out["savings_eur"] = out["savings_eur"].fillna(0.0)
    out["avg_weekly_savings"] = (out["savings_eur"] / num_weeks).round(2)
    out["efficient_weekly_cost"] = (
        (out["avg_weekly_cost"] - out["avg_weekly_savings"]).clip(lower=0).round(2)
    )
    out["headroom"] = out["criticality"].map(_CRITICALITY_HEADROOM)
    out["has_anomaly"] = out["team"].isin(anomaly_teams)
    # Equipos con anomalia activa: el limite objetivo es su coste EFICIENTE (sin
    # holgura), para forzar la bajada que elimina el derroche. El resto: coste
    # eficiente con holgura por criticidad.
    out["recommended_weekly_limit_eur"] = out["efficient_weekly_cost"].where(
        out["has_anomaly"], out["efficient_weekly_cost"] * out["headroom"]
    ).round(2)
    out["avg_weekly_cost"] = out["avg_weekly_cost"].round(2)
    out["savings_eur"] = out["savings_eur"].round(2)

    cols = [
        "team", "criticality", "avg_weekly_cost", "avg_weekly_savings",
        "efficient_weekly_cost", "has_anomaly", "headroom", "recommended_weekly_limit_eur",
    ]
    return out[cols].sort_values("avg_weekly_cost", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
def compute_all_signals(df: pd.DataFrame) -> dict[str, pd.DataFrame | dict]:
    """Calcula todas las señales y devuelve un diccionario nombrado."""
    signals: dict[str, pd.DataFrame | dict] = {
        "cost_by_team": cost_by_dimension(df, "team"),
        "cost_by_user": cost_by_dimension(df, "user_id"),
        "cost_by_project": cost_by_dimension(df, "project"),
        "cost_by_model": cost_by_model(df),
        "task_mix_by_team": task_mix_by_team(df),
        "acceptance_by_team": acceptance_by_dimension(df, "team"),
        "acceptance_by_user": acceptance_by_dimension(df, "user_id"),
        "retry_rate_by_team": retry_rate_by_dimension(df, "team"),
        "weekly_cost_trend": weekly_cost_trend(df, "team"),
        "cost_anomalies": cost_anomalies(df),
        "expensive_on_small_tasks": expensive_on_small_tasks(df),
        "boilerplate_index_by_team": boilerplate_index_by_team(df),
        "recommended_weekly_limits": recommended_weekly_limits(df),
    }
    signals["summary"] = _headline_summary(df, signals)
    return signals


def _headline_summary(df: pd.DataFrame, signals: dict) -> dict:
    """Cifras de titular para el encabezado del dashboard."""
    savings = signals["expensive_on_small_tasks"]
    return {
        "total_events": int(len(df)),
        "total_sessions": int(df["session_id"].nunique()),
        "total_cost_eur": round(float(df["cost_eur"].sum()), 2),
        "weeks": int(df["iso_week"].nunique()),
        "teams": int(df["team"].nunique()),
        "users": int(df["user_id"].nunique()),
        "anomalies_detected": int(len(signals["cost_anomalies"])),
        "estimated_savings_eur": round(float(savings["savings_eur"].sum()), 2) if not savings.empty else 0.0,
    }
