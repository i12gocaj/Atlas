"""Chat de lenguaje natural sobre la telemetria de uso de IA (con tool-use).

Permite preguntar en lenguaje natural ("que equipo gasta mas y por que") y obtener
una respuesta apoyada en las señales DETERMINISTAS, no inventada. El flujo es un
agente de un paso, robusto con modelos locales:

1) El LLM elige UNA herramienta de consulta y sus argumentos (JSON).
2) Ejecutamos la herramienta en Python sobre las señales (cifras reales).
3) El LLM redacta la respuesta citando el resultado de la herramienta.

Las herramientas solo LEEN las señales ya calculadas: el LLM nunca toca los
numeros, solo decide que consultar y como explicarlo. Asi no hay alucinacion de
cifras.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from ..llm.base import LLMError, LLMProvider

# Catalogo de herramientas: nombre -> (descripcion, argumentos).
TOOLS_DOC = {
    "coste_por_equipo": "Coste total por equipo, de mayor a menor. Args: {}",
    "detalle_equipo": "Detalle de un equipo (coste, ahorro, aceptacion, anomalia, limite). Args: {equipo}",
    "anomalias": "Anomalias de coste detectadas semana contra semana. Args: {}",
    "ahorro": "Oportunidades de ahorro por modelo caro en tareas pequenas. Args: {}",
    "aceptacion": "Ratio de aceptacion de sugerencias por equipo. Args: {}",
    "tendencia_equipo": "Coste semana a semana de un equipo. Args: {equipo}",
}

_SELECT_SYSTEM = (
    "Eres un enrutador de consultas. Dada una pregunta sobre el uso de IA de la "
    "organizacion, elige UNA herramienta del catalogo y sus argumentos. Responde "
    "SOLO JSON."
)

_ANSWER_SYSTEM = (
    "Eres Atlas, un agente analista de gobierno del uso de IA. Responde la pregunta "
    "con una o dos FRASES COMPLETAS y naturales en espanol, no con numeros sueltos. "
    "Cita las cifras relevantes con su unidad (EUR, %, equipo). Usa SOLO los numeros "
    "del resultado de la herramienta, no inventes ninguno. Sin guiones largos."
)


def _records(df: pd.DataFrame, n: int = 8) -> list[dict]:
    if df is None or df.empty:
        return []
    return json.loads(df.head(n).to_json(orient="records", force_ascii=False))


def canonical_team(value: object, known: list[str]) -> str | None:
    """Mapea el nombre de equipo que dice el LLM al canonico real.

    El LLM puede devolver "pagos", "Pagos team" o "equipo Pagos": un exact-match
    crudo fallaria. Resolvemos por coincidencia exacta sin mayusculas y luego por
    subcadena, contra la lista de equipos conocidos.
    """
    if not value:
        return None
    v = str(value).strip().lower()
    for team in known:
        if team.lower() == v:
            return team
    for team in known:
        if team.lower() in v or v in team.lower():
            return team
    return None


def _build_tools(signals: dict[str, Any], df: pd.DataFrame) -> dict[str, Callable[[dict], Any]]:
    """Construye el registro de herramientas ejecutables sobre las señales."""
    known_teams = sorted(df["team"].unique())

    def coste_por_equipo(_: dict) -> Any:
        return _records(signals["cost_by_team"])

    def detalle_equipo(args: dict) -> Any:
        equipo = canonical_team(args.get("equipo"), known_teams)
        if equipo is None:
            return {"error": f"equipo no reconocido: {args.get('equipo')!r}", "equipos_validos": known_teams}
        out = {}
        for key in ("cost_by_team", "acceptance_by_team", "recommended_weekly_limits"):
            table = signals[key]
            match = table[table["team"] == equipo]
            if not match.empty:
                out[key] = _records(match, 1)[0]
        return out

    def anomalias(_: dict) -> Any:
        return _records(signals["cost_anomalies"])

    def ahorro(_: dict) -> Any:
        return _records(signals["expensive_on_small_tasks"])

    def aceptacion(_: dict) -> Any:
        return _records(signals["acceptance_by_team"])

    def tendencia_equipo(args: dict) -> Any:
        equipo = canonical_team(args.get("equipo"), known_teams)
        if equipo is None:
            return {"error": f"equipo no reconocido: {args.get('equipo')!r}", "equipos_validos": known_teams}
        trend = signals["weekly_cost_trend"]
        return _records(trend[trend["team"] == equipo], 20)

    return {
        "coste_por_equipo": coste_por_equipo,
        "detalle_equipo": detalle_equipo,
        "anomalias": anomalias,
        "ahorro": ahorro,
        "aceptacion": aceptacion,
        "tendencia_equipo": tendencia_equipo,
    }


def select_tool(provider: LLMProvider, question: str) -> dict:
    """El LLM elige herramienta y argumentos para la pregunta."""
    catalog = "\n".join(f"- {name}: {doc}" for name, doc in TOOLS_DOC.items())
    prompt = (
        f"Catalogo de herramientas:\n{catalog}\n\n"
        f'Pregunta: "{question}"\n\n'
        'Devuelve JSON con esta forma exacta: {"tool": "<nombre>", "args": {<argumentos>}}'
    )
    try:
        result = provider.generate_json(prompt, system=_SELECT_SYSTEM)
    except LLMError:
        result = {}
    tool = str(result.get("tool", "")).strip()
    args = result.get("args")
    if not isinstance(args, dict):  # el LLM podria devolver una lista, string o null
        args = {}
    if tool not in TOOLS_DOC:
        tool = "coste_por_equipo"  # fallback seguro
        args = {}
    return {"tool": tool, "args": args}


def answer(provider: LLMProvider, signals: dict[str, Any], df: pd.DataFrame, question: str) -> dict:
    """Responde una pregunta en lenguaje natural sobre el uso de IA."""
    tools = _build_tools(signals, df)
    choice = select_tool(provider, question)
    tool_result = tools[choice["tool"]](choice["args"])

    prompt = (
        f'Pregunta: "{question}"\n\n'
        f"Herramienta usada: {choice['tool']} con argumentos {json.dumps(choice['args'], ensure_ascii=False)}\n"
        f"Resultado (JSON):\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}\n\n"
        "Responde la pregunta usando solo estos numeros."
    )
    try:
        text = provider.generate(prompt, system=_ANSWER_SYSTEM, temperature=0.1)
    except LLMError:
        # Si el modelo falla, degradamos al dato deterministico (la demo no se rompe).
        text = json.dumps(tool_result, ensure_ascii=False)
    return {"tool": choice["tool"], "args": choice["args"], "tool_result": tool_result, "answer": text}
