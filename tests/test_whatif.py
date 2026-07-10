"""Tests del simulador what-if (contrafactual, determinista)."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.analysis import whatif
from atlas.generation.generator import generate_events
from atlas import config
from atlas.signals import aggregations


@pytest.fixture(scope="module")
def df():
    frame = pd.DataFrame(e.to_dict() for e in generate_events())
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["iso_week"] = frame["timestamp"].dt.strftime("%G-W%V")
    frame["total_tokens"] = frame["input_tokens"] + frame["output_tokens"]
    frame["model_tier"] = frame["model"].map(lambda m: config.MODELS[m].tier)
    return frame


def test_whatif_saved_matches_savings_signal(df):
    w = whatif.simulate_policy(df)
    expected = round(float(aggregations.expensive_on_small_tasks(df)["savings_eur"].sum()), 2)
    # El ahorro contrafactual cuadra con la señal de ahorro del brief.
    assert w["saved_eur"] == expected


def test_whatif_counterfactual_is_lower_and_annualized(df):
    w = whatif.simulate_policy(df)
    assert w["counterfactual_total_eur"] < w["actual_total_eur"]
    assert w["saved_eur"] > 0
    # cada semana el coste con politica es <= coste real
    assert all(r["counterfactual"] <= r["actual"] + 1e-9 for r in w["weekly"])
    # anualizado coherente: low < high y ambos > ahorro de 8 semanas
    assert 0 < w["saved_annual_low_eur"] <= w["saved_annual_high_eur"]
    assert w["saved_annual_high_eur"] > w["saved_eur"]
