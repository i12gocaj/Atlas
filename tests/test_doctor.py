"""Tests del doctor (invariantes deterministas de la demo)."""

from __future__ import annotations

from pathlib import Path

from atlas import doctor, storage
from atlas.generation.generator import generate_events

POLICY_FILE = Path(__file__).parents[1] / "policy.yaml"


def test_doctor_deterministic_invariants_pass(tmp_path):
    events = tmp_path / "events.jsonl"
    storage.write_events_jsonl(generate_events(), events)
    checks = {c.name: c for c in doctor.run_checks(events, tmp_path / "nocache", POLICY_FILE)}

    # El doctor cubre 11 invariantes; fijamos el total para que no se borre ninguno.
    assert len(checks) == 11

    # Los invariantes deterministas (sin LLM) deben pasar con la semilla por defecto.
    # Incluye los dos longitudinales/policy que el doctor existe para proteger.
    for name in (
        "dataset",
        "anomalia_pagos",
        "ahorro_pagos",
        "boilerplate_datos",
        "fuga_secreto",
        "politica_cumplimiento",
        "salud_gobierno",
    ):
        assert checks[name].ok, f"{name}: {checks[name].detail}"

    # Sin cache de LLM/validacion, esas comprobaciones fallan con mensaje claro.
    for name in ("brief_integridad", "validacion_secretos", "validacion_intencion", "validacion_pii"):
        assert checks[name].ok is False


def test_doctor_missing_dataset_fails_clean(tmp_path):
    checks = doctor.run_checks(tmp_path / "no.jsonl", tmp_path)
    assert len(checks) == 1 and checks[0].name == "dataset" and not checks[0].ok
