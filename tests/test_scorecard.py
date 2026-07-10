"""Tests del scorecard de gobernanza continua (longitudinal, determinista)."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas import config
from atlas.analysis import scorecard
from atlas.generation.generator import generate_events


@pytest.fixture(scope="module")
def df():
    frame = pd.DataFrame(e.to_dict() for e in generate_events())
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["iso_week"] = frame["timestamp"].dt.strftime("%G-W%V")
    frame["total_tokens"] = frame["input_tokens"] + frame["output_tokens"]
    frame["model_tier"] = frame["model"].map(lambda m: config.MODELS[m].tier)
    return frame


@pytest.fixture(scope="module")
def sc(df):
    return scorecard.weekly_scorecard(df)


def test_one_score_per_week(sc):
    assert len(sc["weeks"]) == config.SIMULATION.num_weeks


def test_scores_are_bounded_0_100(sc):
    for w in sc["weeks"]:
        assert 0 <= w["score"] <= 100
        for dim in ("seguridad", "coste", "eficiencia", "adopcion"):
            assert 0 <= w[dim] <= 100


def test_health_deteriorates_over_the_period(sc):
    # El pico es alto y la ultima semana esta claramente por debajo: la historia
    # longitudinal es que la gobernanza se degrada cuando los escenarios se activan.
    assert sc["pico"]["score"] >= 90
    assert sc["delta_vs_inicio"] <= -5
    assert sc["latest"]["score"] < sc["pico"]["score"]


def test_weights_sum_to_one():
    assert abs(sum(scorecard.WEIGHTS.values()) - 1.0) < 1e-9


def test_score_is_weighted_average_of_components(sc):
    # El score se calcula sobre las dimensiones YA redondeadas, asi que la
    # reconstruccion desde ellas es exacta (no depende de la tolerancia de redondeo).
    for w in sc["weeks"]:
        expected = (
            scorecard.WEIGHTS["seguridad"] * w["seguridad"]
            + scorecard.WEIGHTS["coste"] * w["coste"]
            + scorecard.WEIGHTS["eficiencia"] * w["eficiencia"]
            + scorecard.WEIGHTS["adopcion"] * w["adopcion"]
        )
        assert w["score"] == round(expected, 1)


def test_empty_df_returns_neutral_without_crashing(df):
    result = scorecard.weekly_scorecard(df.iloc[0:0])
    assert result["weeks"] == []
    assert result["latest"] is None
    assert result["pico"] is None


def test_ceilings_and_threshold_stay_in_sync_with_policy():
    from pathlib import Path

    from atlas.analysis import policy

    reglas = policy.load_policy(Path(__file__).parents[1] / "policy.yaml")["reglas"]
    assert scorecard.DEFAULT_CEILINGS == reglas["techo_coste_semanal"]["techo_eur_por_criticidad"]
    assert scorecard.WASTE_TOKEN_THRESHOLD == reglas["sin_derroche_modelo"]["umbral_tokens"]


def test_deterministic(df):
    assert scorecard.weekly_scorecard(df) == scorecard.weekly_scorecard(df)


def test_secret_weeks_lower_security(sc):
    # Las semanas con fuga tienen seguridad por debajo de 100.
    for w in sc["weeks"]:
        if w["fugas"] > 0:
            assert w["seguridad"] < 100
