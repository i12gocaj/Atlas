"""El agente del brief: hallazgos DETERMINISTAS, prosa del LLM.

Reparto de responsabilidades, alineado con el principio "el LLM solo donde aporta":
- Las CIFRAS, la deteccion de hallazgos, su severidad y las recomendaciones de
  limite las produce codigo DETERMINISTA a partir de las señales. El LLM no toca
  ningun numero (asi no puede alucinarlo ni transcribirlo mal).
- El LLM SOLO redacta lo que una plantilla no hace bien: el resumen ejecutivo en
  prosa y una recomendacion accionable por hallazgo. Eso es lenguaje natural, que
  es donde el LLM aporta valor real.

Si el LLM falla o devuelve algo incompleto, el brief sigue siendo valido (los
hallazgos y cifras estan completos sin el); solo faltaria pulir la prosa.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from ..llm.base import LLMError, LLMProvider
from . import limits

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Umbrales deterministas para elevar una señal a hallazgo.
BOILERPLATE_PCT_THRESHOLD = 20.0
LOW_ACCEPTANCE_THRESHOLD = 0.5

_SYSTEM = (
    "Eres Atlas, un agente analista de gobierno del uso de IA. Te dan HALLAZGOS ya "
    "detectados, con sus cifras exactas. Tu unico trabajo es REDACTAR: no cambies "
    "ni inventes ninguna cifra. Escribe en espanol, claro y ejecutivo, sin guiones "
    "largos. Responde SOLO JSON valido."
)


# ---------------------------------------------------------------------------
# Deteccion determinista de hallazgos (sin LLM)
# ---------------------------------------------------------------------------
def detect_findings(signals: dict[str, Any], extras: dict | None = None) -> list[dict]:
    """Detecta hallazgos a partir de las señales, con cifras reales. Sin LLM."""
    extras = extras or {}
    findings: list[dict] = []

    anomalies = signals.get("cost_anomalies")
    if anomalies is not None and not anomalies.empty:
        for _, a in anomalies.iterrows():
            findings.append(
                {
                    "id": f"anomalia_{a['team']}",
                    "titulo": f"Anomalía de coste en {a['team']}",
                    "severidad": "alta",
                    "evidencia": (
                        f"El coste de {a['team']} pasó de {round(a['prev_cost'], 2)} a "
                        f"{round(a['cost_eur'], 2)} EUR en {a['iso_week']} (x{a['wow_ratio']})."
                    ),
                    "ahorro_eur": None,
                }
            )

    savings = signals.get("expensive_on_small_tasks")
    if savings is not None and not savings.empty:
        top = savings.iloc[0]
        if float(top["savings_eur"]) > 0:
            findings.append(
                {
                    "id": "ahorro",
                    "titulo": f"Ahorro recuperable en {top['team']}",
                    "severidad": "media",
                    "evidencia": (
                        f"{top['team']} usa el modelo caro en {int(top['events'])} tareas "
                        f"pequeñas; pasarlas al modelo barato ahorraría {top['savings_eur']} EUR."
                    ),
                    "ahorro_eur": float(top["savings_eur"]),
                }
            )

    boiler = signals.get("boilerplate_index_by_team")
    if boiler is not None and not boiler.empty:
        b = boiler.iloc[0]
        if float(b["boilerplate_pct"]) >= BOILERPLATE_PCT_THRESHOLD:
            extra = ""
            if extras.get("boilerplate_examples"):
                ex = extras["boilerplate_examples"][0]
                if len(ex) > 80:
                    ex = ex[:80].rsplit(" ", 1)[0] + "…"
                extra = f' Ejemplo: "{ex}".'
            findings.append(
                {
                    "id": "boilerplate",
                    "titulo": f"Boilerplate repetido en {b['team']}",
                    "severidad": "media",
                    "evidencia": (
                        f"El {b['boilerplate_pct']}% de los eventos de {b['team']} son la misma "
                        f"petición repetida, candidata a una plantilla.{extra}"
                    ),
                    "ahorro_eur": None,
                }
            )

    acceptance = signals.get("acceptance_by_team")
    if acceptance is not None and not acceptance.empty:
        worst = acceptance.sort_values("acceptance_rate").iloc[0]
        if float(worst["acceptance_rate"]) < LOW_ACCEPTANCE_THRESHOLD:
            findings.append(
                {
                    "id": "adopcion",
                    "titulo": f"Adopción inmadura en {worst['team']}",
                    "severidad": "media",
                    "evidencia": (
                        f"{worst['team']} tiene la aceptación más baja ({worst['acceptance_rate']}), "
                        "señal de uso poco eficiente de la IA."
                    ),
                    "ahorro_eur": None,
                }
            )

    if extras.get("secret_insight"):
        secrets = extras["secret_insight"]
        teams = sorted({s.get("equipo", "") for s in secrets})
        types = sorted({s.get("tipo", "") for s in secrets if s.get("tipo")})
        findings.append(
            {
                "id": "secretos",
                "titulo": "Posibles secretos en prompts",
                "severidad": "alta",
                "evidencia": (
                    f"Se detectaron {len(secrets)} prompts con posibles secretos en "
                    f"{', '.join(teams)} (tipos: {', '.join(types)})."
                ),
                "ahorro_eur": None,
            }
        )

    return findings


# ---------------------------------------------------------------------------
# Prosa del LLM (lo unico que genera el modelo)
# ---------------------------------------------------------------------------
def _write_prose(provider: LLMProvider, findings: list[dict], summary: dict, temperature: float) -> dict:
    """Pide al LLM SOLO el resumen y una recomendacion por hallazgo (sin cifras nuevas)."""
    import json

    finding_lines = "\n".join(
        f"- id={f['id']} | [{f['severidad']}] {f['titulo']}: {f['evidencia']}" for f in findings
    )
    prompt = (
        f"Resumen numerico de la organizacion: {json.dumps(summary, ensure_ascii=False)}\n\n"
        f"Hallazgos ya detectados (con sus cifras, no las cambies):\n{finding_lines}\n\n"
        "Escribe en espanol de Espana. Usa 'coste' (no 'costo'). Llamalos 'hallazgos "
        "de gobierno', NO 'anomalias': solo el de coste es una anomalia; los demas son "
        "ahorro, trabajo repetitivo, adopcion y secretos.\n"
        "La PRIMERA frase debe ser concreta y con gancho: nombra el hallazgo mas grave "
        "(el pico de coste de un equipo) con su cifra. Nada de frases vacias tipo "
        "'se detectaron hallazgos significativos'. Maximo 3 frases, directas.\n\n"
        "Devuelve JSON con esta forma exacta:\n"
        '{"resumen_ejecutivo": "<2 a 4 frases>", '
        '"recomendaciones": [{"id": "<id del hallazgo>", "recomendacion": "<una frase accionable>"}]}'
    )
    try:
        return provider.generate_json(prompt, system=_SYSTEM, temperature=temperature)
    except LLMError:
        return {"resumen_ejecutivo": "", "recomendaciones": []}


def _extract_numbers(text: str) -> set[float]:
    """Extrae los numeros de un texto como floats (normaliza la coma decimal)."""
    out: set[float] = set()
    for tok in _NUMBER_RE.findall(text or ""):
        try:
            out.add(round(float(tok.replace(",", ".")), 2))
        except ValueError:
            continue
    return out


def _allowed_numbers(findings: list[dict], summary: dict) -> set[float]:
    """Conjunto de cifras DETERMINISTAS que el agente tiene permitido citar."""
    allowed: set[float] = set()
    for v in (summary or {}).values():
        if isinstance(v, (int, float)):
            allowed.add(round(float(v), 2))
    for f in findings:
        allowed |= _extract_numbers(f.get("evidencia", ""))
        allowed |= _extract_numbers(f.get("titulo", ""))
        if f.get("ahorro_eur") is not None:
            allowed.add(round(float(f["ahorro_eur"]), 2))
    return allowed


def verify_numeric_integrity(prose_texts: list[str], allowed: set[float]) -> dict:
    """Comprueba que toda cifra de la prosa del LLM existe en los datos deterministas.

    Es la prueba del principio rector: el LLM redacta, pero NO introduce ningun
    numero que no venga de las señales. Si encuentra una cifra inventada, la lista.
    """
    invented: list[float] = []
    checked = 0
    for text in prose_texts:
        for n in _extract_numbers(text):
            checked += 1
            # Ignora los anos (2000-2099 enteros, p.ej. de "2026-W18").
            if 2000 <= n <= 2099 and n == int(n):
                continue
            # Se compara con tolerancia de centimo.
            if not any(abs(n - a) <= 0.01 for a in allowed):
                invented.append(n)
    return {"checked": checked, "invented": sorted(set(invented)), "ok": not invented}


def _fallback_resumen(summary: dict, findings: list[dict]) -> str:
    """Resumen 100% deterministico, por si el LLM introdujese una cifra inventada."""
    sev_alta = [f["titulo"] for f in findings if f.get("severidad") == "alta"]
    cierre = f" Hallazgos de alta prioridad: {'; '.join(sev_alta)}." if sev_alta else ""
    return (
        f"Se observaron {summary.get('total_events', 0)} interacciones con IA en "
        f"{summary.get('weeks', 0)} semanas, con un coste total de "
        f"{summary.get('total_cost_eur', 0)} EUR. Se detectaron {len(findings)} hallazgos."
        f"{cierre}"
    )


def generate_brief(
    provider: LLMProvider,
    signals: dict[str, Any],
    extras: dict | None = None,
    temperature: float = 0.2,
) -> dict:
    """Genera el brief: hallazgos y limites deterministas, prosa del LLM verificada."""
    summary = signals.get("summary", {})
    findings = detect_findings(signals, extras)
    recomendaciones_limite = limits.build_recommendations(signals["recommended_weekly_limits"])

    prose = _write_prose(provider, findings, summary, temperature)
    rec_by_id = {r.get("id"): (r.get("recomendacion") or "").strip() for r in prose.get("recomendaciones", [])}
    for f in findings:
        f["recomendacion"] = rec_by_id.get(f["id"], "")

    # Verificacion de integridad numerica: el LLM no puede colar una cifra que no
    # este en los datos deterministas. Se verifica el resumen y CADA recomendacion
    # por separado: una cifra inventada en una recomendacion la vacia (el render
    # omite recomendaciones vacias) sin publicarse jamas, y un resumen limpio no
    # se descarta por el fallo de una recomendacion.
    resumen = (prose.get("resumen_ejecutivo") or "").strip()
    allowed = _allowed_numbers(findings, summary)

    checked = 0
    invented: list[float] = []
    fallback_used = False

    res_check = verify_numeric_integrity([resumen], allowed)
    checked += res_check["checked"]
    invented += res_check["invented"]
    if not res_check["ok"]:
        resumen = _fallback_resumen(summary, findings)
        fallback_used = True

    for f in findings:
        rec_check = verify_numeric_integrity([f.get("recomendacion", "")], allowed)
        checked += rec_check["checked"]
        invented += rec_check["invented"]
        if not rec_check["ok"]:
            f["recomendacion"] = ""
            fallback_used = True

    integrity = {"checked": checked, "invented": sorted(set(invented)), "ok": not invented}
    if fallback_used:
        integrity["fallback_used"] = True

    return {
        "resumen_ejecutivo": resumen,
        "hallazgos": findings,
        "recomendaciones_limite": recomendaciones_limite,
        "integrity": integrity,
        "_meta": {"provider": provider.name, "model": provider.model},
    }


def gather_extras(df: pd.DataFrame) -> dict:
    """Reune ejemplos de contenido para enriquecer los hallazgos (boilerplate, secretos)."""
    extras: dict = {}
    boiler = df[df["gt_is_boilerplate"]]["prompt_text"].head(3).tolist()
    if boiler:
        extras["boilerplate_examples"] = boiler
    secrets = df[df["gt_contains_secret"]]
    if not secrets.empty:
        extras["secret_insight"] = [
            {"equipo": r["team"], "tipo": r["gt_secret_type"], "fragmento": r["prompt_text"][:120]}
            for _, r in secrets.iterrows()
        ]
    return extras


def render_markdown(brief: dict) -> str:
    """Renderiza el brief a Markdown para mostrarlo o exportarlo."""
    lines = ["# Brief de gobernanza de IA, Atlas", ""]
    meta = brief.get("_meta", {})
    if meta:
        lines.append(f"_Cifras deterministas. Prosa por {meta.get('provider')}:{meta.get('model')}_")
        lines.append("")
    if brief.get("resumen_ejecutivo"):
        lines.append("## Resumen ejecutivo")
        lines.append(brief["resumen_ejecutivo"])
        lines.append("")
    if brief.get("hallazgos"):
        lines.append("## Hallazgos")
        for h in brief["hallazgos"]:
            sev = str(h.get("severidad", "")).upper()
            lines.append(f"### [{sev}] {h.get('titulo', '')}")
            if h.get("evidencia"):
                lines.append(f"- Evidencia: {h['evidencia']}")
            if h.get("recomendacion"):
                lines.append(f"- Recomendacion: {h['recomendacion']}")
            if h.get("ahorro_eur"):
                lines.append(f"- Ahorro estimado: {h['ahorro_eur']} EUR")
            lines.append("")
    if brief.get("recomendaciones_limite"):
        lines.append("## Recomendaciones de limite por equipo")
        for r in brief["recomendaciones_limite"]:
            lines.append(f"- {r.get('equipo', '')}: {str(r.get('accion', '')).upper()}. {r.get('motivo', '')}")
        lines.append("")
    return "\n".join(lines)
