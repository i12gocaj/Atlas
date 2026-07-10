"""Tests del arnes de validacion sobre el set gold (plumbing, con stub)."""

from __future__ import annotations

import json

from atlas import validation
from atlas.llm import StubProvider


def test_wilson_interval():
    lo, hi = validation.wilson_interval(18, 18)
    assert hi == 1.0 and 0.7 < lo < 1.0  # recall perfecto sobre 18 no es 1.0 de verdad
    assert validation.wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = validation.wilson_interval(10, 20)
    assert lo < 0.5 < hi


def test_gold_sets_load_and_are_labeled():
    secrets = validation.load_jsonl(validation.DEFAULT_VALIDATION_DIR / "secrets_nl.jsonl")
    intent = validation.load_jsonl(validation.DEFAULT_VALIDATION_DIR / "intent.jsonl")
    # Secretos: hay positivos y negativos, y casos en lenguaje natural (password).
    assert any(r["contains_secret"] for r in secrets)
    assert any(not r["contains_secret"] for r in secrets)
    assert any(r.get("secret_type") == "password" for r in secrets)
    assert any(r.get("hard_negative") for r in secrets)
    # Intencion: estan las 6 categorias y los dos idiomas.
    cats = {r["category"] for r in intent}
    assert cats == {"codigo", "documentacion", "pruebas", "requisitos", "debug", "analisis"}
    assert {r["lang"] for r in intent} == {"es", "en"}


def test_evaluate_secrets_structure_with_stub():
    # Stub que dice que NO hay secreto: aisla la baseline (herramienta).
    stub = StubProvider(lambda p, s: json.dumps({"contains_secret": False, "secret_type": None}))
    rep = validation.evaluate_secrets(stub)
    assert set(rep) >= {"baseline", "llm", "lenguaje_natural", "negativos_dificiles"}
    # La baseline (herramienta) caza los secretos estructurados, el stub-LLM ninguno.
    assert rep["baseline"]["tp"] >= 1
    assert rep["llm"]["recall"] == 0.0


def test_evaluate_intent_structure_with_stub():
    stub = StubProvider(lambda p, s: json.dumps({"category": "codigo"}))
    rep = validation.evaluate_intent(stub)
    assert 0.0 <= rep["llm_accuracy"] <= 1.0
    assert 0.0 <= rep["rule_accuracy"] <= 1.0
    assert set(rep["por_idioma"]) == {"es", "en"}
