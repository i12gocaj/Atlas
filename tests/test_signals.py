"""Tests de la capa de señales sobre el dataset generado."""

from __future__ import annotations

import pandas as pd
import pytest

from atlas import config
from atlas.generation.generator import generate_events
from atlas.signals import aggregations


@pytest.fixture(scope="module")
def df():
    events = generate_events()
    frame = pd.DataFrame(e.to_dict() for e in events)
    # Replicamos el enriquecimiento que hace load_dataframe.
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["iso_week"] = frame["timestamp"].dt.strftime("%G-W%V")
    frame["total_tokens"] = frame["input_tokens"] + frame["output_tokens"]
    frame["model_tier"] = frame["model"].map(lambda m: config.MODELS[m].tier)
    return frame


def test_cost_by_team_sums_to_total(df):
    by_team = aggregations.cost_by_dimension(df, "team")
    assert abs(by_team["cost_eur"].sum() - df["cost_eur"].sum()) < 1e-6


def test_task_mix_percentages_sum_100_per_team(df):
    mix = aggregations.task_mix_by_team(df)
    totals = mix.groupby("team")["pct"].sum()
    for team, total in totals.items():
        assert abs(total - 100.0) < 0.5, team


def test_anomaly_detection_flags_pagos(df):
    anomalies = aggregations.cost_anomalies(df)
    assert not anomalies.empty
    assert config.SCENARIOS.cost_spike_team in set(anomalies["team"])


def test_expensive_on_small_tasks_finds_savings(df):
    savings = aggregations.expensive_on_small_tasks(df)
    assert not savings.empty
    assert savings["savings_eur"].sum() > 0


def test_summary_has_headline_numbers(df):
    signals = aggregations.compute_all_signals(df)
    summary = signals["summary"]
    assert summary["total_events"] == len(df)
    assert summary["anomalies_detected"] >= 1
    assert summary["estimated_savings_eur"] > 0


def test_recommended_limits_respect_criticality(df):
    limits = aggregations.recommended_weekly_limits(df)
    # Todos los equipos tienen un limite recomendado positivo.
    assert (limits["recommended_weekly_limit_eur"] > 0).all()
    assert set(limits["team"]) == {t.name for t in config.TEAMS}
