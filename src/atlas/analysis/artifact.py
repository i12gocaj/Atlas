"""Artefacto de gobernanza: propuesta de limites por equipo, firmada por el agente.

Es la salida tangible de la cadena de valor: no una grafica que interpretar, sino
una decision lista para llevar al comite. Toma la tabla de limites deterministas
(coste actual, ahorro recuperable, limite recomendado, anomalia) y firma la
propuesta con el modelo y la fecha.

Principio rector: la ACCION (subir/mantener/bajar/optimizar) la decide siempre la
regla DETERMINISTA y consciente del derroche (a un equipo con anomalia o ahorro
recuperable alto nunca se le propone subir). El LLM no decide ni sobreescribe la
accion: como mucho aporta una version mas legible del MOTIVO, y solo si su
recomendacion coincide con la regla. Asi el gobierno no depende de que el LLM
"acierte" la decision.
"""

from __future__ import annotations

import pandas as pd

from .limits import decide_action


def build_limit_proposal(
    limits: pd.DataFrame,
    generated_at: str,
    signed_by: str,
    brief: dict | None = None,
) -> dict:
    """Construye la propuesta de limites. Si hay brief, usa la accion del agente."""
    brief_actions: dict[str, dict] = {}
    if brief:
        for rec in brief.get("recomendaciones_limite", []):
            equipo = rec.get("equipo")
            if equipo:
                brief_actions[equipo] = rec

    rows = []
    for _, row in limits.iterrows():
        team = row["team"]
        # La accion la decide SIEMPRE la regla deterministica (consciente del
        # derroche). El LLM nunca la sobreescribe: solo puede matizar el motivo en
        # prosa, y solo si su recomendacion coincide con la accion deterministica.
        action, motivo = decide_action(row)
        motivo_origen = "determinista"
        brief_rec = brief_actions.get(team)
        if brief_rec and str(brief_rec.get("accion", "")).lower() == action:
            motivo = brief_rec.get("motivo") or motivo
            motivo_origen = "agente"
        rows.append(
            {
                "equipo": team,
                "criticidad": row["criticality"],
                "coste_semanal_actual_eur": round(float(row["avg_weekly_cost"]), 2),
                "ahorro_semanal_recuperable_eur": round(float(row["avg_weekly_savings"]), 2),
                "limite_semanal_propuesto_eur": round(float(row["recommended_weekly_limit_eur"]), 2),
                "accion": action,
                "motivo": motivo,
                "origen_accion": "determinista",
                "motivo_origen": motivo_origen,
            }
        )

    total_savings = round(sum(r["ahorro_semanal_recuperable_eur"] for r in rows), 2)
    return {
        "titulo": "Propuesta de límites de uso de IA por equipo",
        "generado": generated_at,
        "firmado_por": signed_by,
        "ahorro_semanal_total_recuperable_eur": total_savings,
        "lineas": rows,
    }


def render_markdown(proposal: dict) -> str:
    """Renderiza la propuesta a Markdown, lista para descargar o llevar al comite."""
    lines = [f"# {proposal['titulo']}", ""]
    lines.append(f"Generado: {proposal['generado']}")
    lines.append(f"Firmado por: {proposal['firmado_por']} (agente Atlas, read-only)")
    lines.append(f"Ahorro semanal total recuperable: {proposal['ahorro_semanal_total_recuperable_eur']} EUR")
    lines.append("")
    lines.append("| Equipo | Criticidad | Coste/sem | Ahorro/sem | Límite propuesto | Acción | Motivo |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in proposal["lineas"]:
        lines.append(
            f"| {r['equipo']} | {r['criticidad']} | {r['coste_semanal_actual_eur']} | "
            f"{r['ahorro_semanal_recuperable_eur']} | {r['limite_semanal_propuesto_eur']} | "
            f"{r['accion'].upper()} | {r['motivo']} |"
        )
    lines.append("")
    lines.append(
        "_Propuesta generada por un agente de IA en modo read-only. Es una "
        "recomendación: la decisión final es humana._"
    )
    return "\n".join(lines)


def to_csv_rows(proposal: dict) -> pd.DataFrame:
    """Devuelve las lineas de la propuesta como DataFrame (para exportar a CSV)."""
    return pd.DataFrame(proposal["lineas"])
