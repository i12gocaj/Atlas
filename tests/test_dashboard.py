"""Tests del exportador de datos del dashboard (parte determinista, sin LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from atlas import dashboard, storage
from atlas.generation.generator import generate_events

REPO = Path(__file__).parents[1]
POLICY_FILE = REPO / "policy.yaml"


def _events_file(tmp_path):
    path = tmp_path / "events.jsonl"
    storage.write_events_jsonl(generate_events(), path)
    return path


def test_dashboard_data_has_deterministic_sections(tmp_path):
    events = _events_file(tmp_path)
    empty_cache = tmp_path / "cache"  # sin brief/boilerplate/validacion
    data = dashboard.build_dashboard_data(events, empty_cache)

    # Meta y señales deterministas siempre presentes.
    assert data["meta"]["events"] > 3000
    assert data["meta"]["teams"] == 5
    assert data["cost_by_team"] and data["cost_by_team"][0]["team"]
    assert data["anomaly"]["team"] == "Pagos"
    assert len(data["spike_trend"]) == 8
    assert data["nl_secret"]["team"] == "Plataforma"

    # Control y tendencia (deterministas, no dependen de la cache de LLM).
    assert data["policy"]["cumplimiento_pct"] == 80.0
    assert data["scorecard"]["latest"]["score"] == 78.2

    # Pico de coste por equipo para el simulador del techo (determinista).
    peaks = data["team_peaks"]
    assert len(peaks) == 5
    vals = [p["peak_eur"] for p in peaks]
    assert vals == sorted(vals, reverse=True)  # ordenado de mayor a menor pico
    assert peaks[0]["team"] == "Pagos"  # el del escenario sembrado
    assert 90 <= peaks[0]["peak_eur"] <= 105

    # Sin cache de LLM/validacion, esas secciones se omiten con elegancia.
    assert data["brief"] is None
    assert data["evidence"] == {}


def test_snapshot_demo_is_fresh(tmp_path):
    """El snapshot versionado (data.demo.json) debe cuadrar con un build fresco.

    Asi, si alguien toca el generador o las senales y olvida 'make snapshot', el
    fallback offline no se queda con cifras obsoletas en silencio.
    """
    demo = json.loads((REPO / "dashboard" / "data.demo.json").read_text(encoding="utf-8"))
    fresh = dashboard.build_dashboard_data(_events_file(tmp_path), tmp_path / "cache", POLICY_FILE)

    assert fresh["meta"]["events"] == demo["meta"]["events"]
    assert fresh["meta"]["total_cost_eur"] == demo["meta"]["total_cost_eur"]
    assert fresh["policy"]["cumplimiento_pct"] == demo["policy"]["cumplimiento_pct"]
    assert fresh["policy"]["incumplimientos"] == demo["policy"]["incumplimientos"]
    assert fresh["scorecard"]["latest"]["score"] == demo["scorecard"]["latest"]["score"]
    assert fresh["scorecard"]["pico"]["score"] == demo["scorecard"]["pico"]["score"]
    assert fresh["savings"]["savings_eur"] == demo["savings"]["savings_eur"]
    assert fresh["whatif"]["saved_eur"] == demo["whatif"]["saved_eur"]
    assert fresh["anomaly"]["wow_ratio"] == demo["anomaly"]["wow_ratio"]
    assert fresh["team_peaks"] == demo["team_peaks"]


def test_dashboard_export_writes_data_js(tmp_path):
    events = _events_file(tmp_path)
    out = tmp_path / "dash" / "data.json"
    dashboard.export(events, out, tmp_path / "cache")
    assert out.exists()
    data_js = out.parent / "data.js"
    assert data_js.exists()
    assert data_js.read_text(encoding="utf-8").startswith("window.ATLAS_DATA = ")
