"""Tests del motor de politicas (determinista, sin LLM)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from atlas import config
from atlas.analysis import policy
from atlas.generation.generator import generate_events

POLICY_FILE = Path(__file__).parents[1] / "policy.yaml"


@pytest.fixture(scope="module")
def df():
    frame = pd.DataFrame(e.to_dict() for e in generate_events())
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["iso_week"] = frame["timestamp"].dt.strftime("%G-W%V")
    frame["total_tokens"] = frame["input_tokens"] + frame["output_tokens"]
    frame["model_tier"] = frame["model"].map(lambda m: config.MODELS[m].tier)
    return frame


@pytest.fixture(scope="module")
def result(df):
    return policy.evaluate(df, policy.load_policy(POLICY_FILE))


def test_compliance_headline(result):
    # 5 reglas x 5 equipos = 25 comprobaciones, 5 incumplimientos -> 80%.
    assert result["comprobaciones"] == 25
    assert result["incumplimientos"] == 5
    assert result["cumplimiento_pct"] == 80.0


def test_compliance_math_is_consistent(result):
    passed = result["comprobaciones"] - result["incumplimientos"]
    assert result["cumplimiento_pct"] == round(passed / result["comprobaciones"] * 100, 1)


def test_core_banking_is_the_model_team(result):
    by_team = {t["equipo"]: t for t in result["por_equipo"]}
    assert by_team["Core Banking"]["incumplimientos"] == 0
    assert by_team["Core Banking"]["cumplimiento_pct"] == 100.0


def test_each_seeded_scenario_breaks_one_rule(result):
    pairs = {(v["equipo"], v["regla"]) for v in result["violaciones"]}
    assert ("Plataforma", "cero_secretos") in pairs
    assert ("Pagos", "techo_coste_semanal") in pairs
    assert ("Pagos", "sin_derroche_modelo") in pairs
    assert ("Equipo Nuevo", "aceptacion_minima") in pairs
    assert ("Datos", "automatizar_boilerplate") in pairs


def test_violations_sorted_by_severity(result):
    order = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
    severities = [order[v["severidad"]] for v in result["violaciones"]]
    assert severities == sorted(severities)
    # lo critico (secreto) va primero.
    assert result["violaciones"][0]["severidad"] == "critica"


def test_every_violation_has_evidence_and_remediation(result):
    for v in result["violaciones"]:
        assert v["detalle"] and isinstance(v["detalle"], str)
        assert v["remediacion"] and isinstance(v["remediacion"], str)
        assert v["titulo"] and v["severidad"]


def test_engine_is_deterministic(df):
    a = policy.evaluate(df, policy.load_policy(POLICY_FILE))
    b = policy.evaluate(df, policy.load_policy(POLICY_FILE))
    assert a == b


def test_savings_coherent_across_signals_whatif_and_policy(df, result):
    # El mismo ahorro (84,66) debe salir por las tres vias: la senal, el what-if
    # y el 'observado' del incumplimiento de derroche. Es el argumento de la demo.
    from atlas.analysis import whatif
    from atlas.signals import aggregations

    signal = round(float(aggregations.expensive_on_small_tasks(df)["savings_eur"].sum()), 2)
    whatif_saved = whatif.simulate_policy(df)["saved_eur"]
    policy_observed = next(
        v["observado"] for v in result["violaciones"] if v["regla"] == "sin_derroche_modelo"
    )
    assert signal == whatif_saved == policy_observed
