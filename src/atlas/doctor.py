"""Doctor: valida los invariantes de la demo antes del pitch.

Comprueba que las cifras clave que cuenta el dashboard no se han desviado al
regenerar (dataset, pico de coste, ahorro, boilerplate, validacion, integridad
del brief). Devuelve PASS/FAIL por comprobacion y un codigo de salida distinto de
cero si algo falla, para poder encadenarlo en `make demo`.

Lee el dataset y las cache de LLM/validacion de un directorio de datos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .analysis import policy as policy_mod
from .analysis import scorecard as scorecard_mod
from .signals import aggregations


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _in_range(value, low, high) -> bool:
    return value is not None and low <= value <= high


def run_checks(
    events_path: str | Path = "data/events.jsonl",
    data_dir: str | Path = "data",
    policy_path: str | Path = "policy.yaml",
) -> list[Check]:
    """Ejecuta todas las comprobaciones y devuelve la lista de resultados."""
    events_path = Path(events_path)
    data_dir = Path(data_dir)
    checks: list[Check] = []

    if not events_path.exists():
        return [Check("dataset", False, f"no existe {events_path}; ejecuta 'atlas generate'")]

    df = aggregations.load_dataframe(events_path)
    n = len(df)
    checks.append(Check("dataset", _in_range(n, 6000, 7600), f"{n} eventos (esperado 6000-7600)"))

    signals = aggregations.compute_all_signals(df)

    anomalies = signals["cost_anomalies"]
    if not anomalies.empty:
        a = anomalies.iloc[0]
        ratio = float(a["wow_ratio"])
        ok = a["team"] == "Pagos" and _in_range(ratio, 3.5, 5.0)
        checks.append(Check("anomalia_pagos", ok, f"{a['team']} x{ratio} (esperado Pagos 3.5-5.0)"))
    else:
        checks.append(Check("anomalia_pagos", False, "no se detecto ninguna anomalia"))

    savings = signals["expensive_on_small_tasks"]
    sv = float(savings.iloc[0]["savings_eur"]) if not savings.empty else None
    checks.append(Check("ahorro_pagos", _in_range(sv, 70, 100), f"{sv} EUR (esperado 70-100)"))

    boiler = signals["boilerplate_index_by_team"]
    bp = float(boiler.iloc[0]["boilerplate_pct"]) if not boiler.empty else None
    checks.append(Check("boilerplate_datos", _in_range(bp, 30, 45), f"{bp}% (esperado 30-45)"))

    secrets = int(df["gt_contains_secret"].sum())
    checks.append(Check("fuga_secreto", secrets >= 1, f"{secrets} secretos sembrados (esperado >= 1)"))

    # Cuadro de cumplimiento (determinista). Esperado: 80% global, 5 incumplimientos,
    # Core Banking como equipo modelo (100%).
    policy_file = Path(policy_path)
    ceilings = scorecard_mod.DEFAULT_CEILINGS
    token_threshold = scorecard_mod.WASTE_TOKEN_THRESHOLD
    if policy_file.exists():
        policy_obj = policy_mod.load_policy(policy_file)
        pr = policy_mod.evaluate(df, policy_obj)
        reglas = policy_obj["reglas"]
        ceilings = reglas["techo_coste_semanal"]["techo_eur_por_criticidad"]
        token_threshold = int(reglas["sin_derroche_modelo"]["umbral_tokens"])
        core = next((t for t in pr["por_equipo"] if t["equipo"] == "Core Banking"), None)
        ok = (
            _in_range(pr["cumplimiento_pct"], 70, 90)
            and pr["incumplimientos"] == 5
            and core is not None
            and core["cumplimiento_pct"] == 100.0
        )
        checks.append(
            Check(
                "politica_cumplimiento",
                ok,
                f"{pr['cumplimiento_pct']}% global, {pr['incumplimientos']} incumplimientos, "
                f"Core Banking {core['cumplimiento_pct'] if core else '?'}%",
            )
        )
    else:
        checks.append(Check("politica_cumplimiento", False, "falta policy.yaml"))

    # Salud de gobierno: la tendencia debe mostrar deterioro (pico alto, caida al
    # final cuando los escenarios se activan), que es la historia longitudinal.
    sc = scorecard_mod.weekly_scorecard(df, ceilings, token_threshold)
    ok = (
        _in_range(sc["latest"]["score"], 70, 85)
        and sc["pico"]["score"] >= 90
        and sc["delta_vs_inicio"] <= -5
    )
    checks.append(
        Check(
            "salud_gobierno",
            ok,
            f"ultima {sc['latest']['score']}, pico {sc['pico']['score']}, "
            f"delta inicio {sc['delta_vs_inicio']}",
        )
    )

    # Cache que depende del LLM.
    brief = _load(data_dir / "brief.json")
    if brief:
        ig = brief.get("integrity", {})
        checks.append(Check("brief_integridad", bool(ig.get("ok")), f"integridad {ig}"))
    else:
        checks.append(Check("brief_integridad", False, "falta data/brief.json (ejecuta 'atlas brief')"))

    vsec = _load(data_dir / "validate_secrets.json")
    if vsec:
        nl = vsec["lenguaje_natural"]
        ok = nl["recall_llm"] == 1.0 and nl["recall_baseline"] == 0.0
        checks.append(Check("validacion_secretos", ok, f"herramienta {nl['recall_baseline']} vs LLM {nl['recall_llm']}"))
    else:
        checks.append(Check("validacion_secretos", False, "falta validate_secrets.json"))

    vint = _load(data_dir / "validate_intent.json")
    if vint:
        ok = vint["llm_accuracy"] >= 0.9 and vint["rule_accuracy"] <= 0.7
        checks.append(Check("validacion_intencion", ok, f"reglas {vint['rule_accuracy']} vs LLM {vint['llm_accuracy']}"))
    else:
        checks.append(Check("validacion_intencion", False, "falta validate_intent.json"))

    vpii = _load(data_dir / "validate_pii.json")
    if vpii:
        h, s = vpii["herramienta"], vpii["senuelos"]
        type_err = vpii.get("errores_de_tipo", 0)
        ok = h["precision"] == 1.0 and h["recall"] == 1.0 and s["falsos_positivos"] == 0 and type_err == 0
        checks.append(
            Check(
                "validacion_pii",
                ok,
                f"precision {h['precision']}, recall {h['recall']}, "
                f"{s['falsos_positivos']} FP en {s['n']} senuelos, {type_err} errores de tipo",
            )
        )
    else:
        checks.append(Check("validacion_pii", False, "falta validate_pii.json (ejecuta 'atlas validate-pii')"))

    return checks


def format_report(checks: list[Check]) -> str:
    """Formatea el informe del doctor para la terminal."""
    lines = []
    for c in checks:
        mark = "PASS" if c.ok else "FAIL"
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    n_ok = sum(1 for c in checks if c.ok)
    lines.append(f"\n{n_ok}/{len(checks)} comprobaciones OK")
    return "\n".join(lines)
