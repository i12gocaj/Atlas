"""Tests del generador: determinismo y presencia de los escenarios sembrados.

Estos tests son la red de seguridad de la demo: garantizan que el dataset es
reproducible y que las cuatro senales que el agente debe encontrar estan ahi de
verdad.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas import config
from atlas.generation.generator import generate_events


@pytest.fixture(scope="module")
def events():
    return generate_events()


@pytest.fixture(scope="module")
def df(events):
    return pd.DataFrame(e.to_dict() for e in events)


def test_dataset_is_deterministic():
    a = generate_events()
    b = generate_events()
    assert [e.to_json_line() for e in a] == [e.to_json_line() for e in b]


def test_dataset_has_reasonable_volume(events):
    # Varios miles de eventos: suficiente para que la demo respire.
    assert len(events) > 3000


def test_all_teams_and_users_present(df):
    assert set(df["team"]) == {t.name for t in config.TEAMS}
    expected_users = {u for t in config.TEAMS for u in t.users}
    assert set(df["user_id"]) == expected_users


def test_cost_matches_tokens_and_tariff(df):
    # El coste debe ser exactamente el derivado de tokens por tarifa.
    sample = df.sample(min(50, len(df)), random_state=0)
    for _, row in sample.iterrows():
        tariff = config.MODELS[row["model"]]
        expected = round(
            row["input_tokens"] / 1000 * tariff.price_per_1k_input
            + row["output_tokens"] / 1000 * tariff.price_per_1k_output,
            4,
        )
        assert abs(row["cost_eur"] - expected) < 1e-9


def test_scenario_cost_spike_pagos(df):
    # Pagos debe disparar su coste a partir de la semana del pico.
    pagos = df[df["team"] == config.SCENARIOS.cost_spike_team].copy()
    pagos["timestamp"] = pd.to_datetime(pagos["timestamp"])
    pagos = pagos.sort_values("timestamp")
    weekly = pagos.groupby(pagos["timestamp"].dt.strftime("%G-W%V"))["cost_eur"].sum()
    # El maximo semanal debe ser muy superior al minimo (pico claro).
    assert weekly.max() > 2.5 * weekly.min()
    # Y debe existir el tag de escenario en los eventos triviales.
    assert (pagos["gt_scenario"] == "cost_spike").any()


def test_scenario_boilerplate_datos(df):
    # El boilerplate es la peticion inicial (primer intento), no los reintentos.
    datos = df[(df["team"] == config.SCENARIOS.boilerplate_team) & (~df["is_retry"])]
    boiler_pct = datos["gt_is_boilerplate"].mean()
    # Alrededor de la fraccion de sesiones configurada (0.40), con holgura.
    assert 0.30 < boiler_pct < 0.55


def test_scenario_secret_leaks_plataforma(df):
    secrets = df[df["gt_contains_secret"]]
    assert len(secrets) == config.SCENARIOS.secret_leak_count
    assert set(secrets["team"]) == {config.SCENARIOS.secret_leak_team}
    # Debe haber al menos una contrasena en lenguaje natural (la que reta al LLM).
    assert "password" in set(secrets["gt_secret_type"])


def test_scenario_low_acceptance_equipo_nuevo(df):
    def session_acceptance(team_df):
        per_session = team_df.groupby("session_id")["accepted"].any()
        return per_session.mean()

    nuevo = session_acceptance(df[df["team"] == config.SCENARIOS.low_acceptance_team])
    core = session_acceptance(df[df["team"] == "Core Banking"])
    # El equipo nuevo debe aceptar claramente menos que un equipo maduro.
    assert nuevo < core


def test_retry_chains_have_consistent_parent(df):
    retries = df[df["is_retry"]]
    assert retries["retry_of"].notna().all()
    first_attempts = df[~df["is_retry"]]
    assert first_attempts["retry_of"].isna().all()
