"""Tests de la capa de analisis (clasificador, secretos LLM, brief) con stub.

Usamos StubProvider para no depender de un modelo real: los tests son rapidos,
deterministas y verifican la LOGICA de la capa (muestreo, metricas, contraste,
construccion del contexto del brief), no la calidad del LLM.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from atlas import config
from atlas.analysis import artifact as artifact_mod
from atlas.analysis import boilerplate as boilerplate_mod
from atlas.analysis import brief as brief_mod
from atlas.analysis import chat as chat_mod
from atlas.analysis import classifier, secrets_llm
from atlas.generation.generator import generate_events
from atlas.llm import StubProvider
from atlas.signals import aggregations


@pytest.fixture(scope="module")
def df():
    frame = pd.DataFrame(e.to_dict() for e in generate_events())
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["iso_week"] = frame["timestamp"].dt.strftime("%G-W%V")
    frame["total_tokens"] = frame["input_tokens"] + frame["output_tokens"]
    frame["model_tier"] = frame["model"].map(lambda m: config.MODELS[m].tier)
    return frame


# --- Clasificador ---
def test_rule_classify_basic():
    assert classifier.rule_classify("el proceso da error, arregla esto") == "debug"
    assert classifier.rule_classify("ponme tests unitarios con pytest") == "pruebas"
    assert classifier.rule_classify("documenta la tabla ventas") == "documentacion"


def test_llm_classify_normalizes_invalid_category():
    stub = StubProvider(lambda p, s: '{"category": "INVENTADA"}')
    assert classifier.llm_classify(stub, "lo que sea") == "desconocida"


def test_evaluate_classifiers_perfect_oracle(df):
    # Un stub que devuelve siempre la categoria correcta leyendola del prompt
    # no es posible aqui, asi que usamos uno que devuelve 'codigo' siempre y
    # comprobamos que las cuentas cuadran.
    stub = StubProvider(lambda p, s: '{"category": "codigo"}')
    report = classifier.evaluate_classifiers(stub, df, per_category=2, seed=0)
    assert report["n"] > 0
    assert 0.0 <= report["llm_accuracy"] <= 1.0
    assert 0.0 <= report["rule_accuracy"] <= 1.0
    assert len(report["details"]) == report["n"]


# --- Deteccion de secretos por LLM ---
def test_llm_detect_secret_parsing():
    stub = StubProvider(
        lambda p, s: '{"contains_secret": true, "secret_type": "password", "evidence": "verano2024"}'
    )
    out = secrets_llm.llm_detect_secret(stub, "la clave admin es verano2024")
    assert out["contains_secret"] is True
    assert out["secret_type"] == "password"


def test_secret_eval_llm_beats_baseline_on_nl_password(df):
    # Stub que detecta secreto cuando el texto menciona 'clave' o tiene patrones
    # tipicos. Asi simulamos el LLM que caza la contrasena en lenguaje natural.
    def responder(prompt: str, system) -> str:
        text = prompt.lower()
        hit = any(k in text for k in ["clave", "password", "token", "key", "://", "akia"])
        stype = "password" if "clave" in text else "api_key"
        return json.dumps({"contains_secret": hit, "secret_type": stype, "evidence": ""})

    stub = StubProvider(responder)
    report = secrets_llm.evaluate_secret_detection(stub, df, neg_sample=15, seed=0)
    # El LLM simulado debe recuperar mas que la baseline (caza la NL password).
    assert report["llm"]["recall"] >= report["baseline"]["recall"]
    assert len(report["caught_by_llm_only"]) >= 1
    assert any(c["gt_secret_type"] == "password" for c in report["caught_by_llm_only"])


# --- Boilerplate (deteccion sin LLM) ---
def test_boilerplate_tokenize_removes_stopwords():
    toks = boilerplate_mod._tokenize("Crea el script de carga para la tabla ventas")
    assert "script" in toks and "carga" in toks
    assert "el" not in toks and "de" not in toks and "la" not in toks


def test_boilerplate_detection_matches_ground_truth(df):
    # La deteccion NO usa gt_is_boilerplate; validamos contra el despues.
    report = boilerplate_mod.analyze_team(df, "Datos", provider=None)
    v = report["validation_vs_gt"]
    assert v["precision"] >= 0.9
    assert v["recall"] >= 0.9
    # Detecta una fraccion notable del equipo como boilerplate (rango amplio
    # para no ser fragil ante ajustes menores del umbral).
    assert 30 <= report["detected_pct"] <= 55


def test_boilerplate_no_false_positives_across_teams(df):
    # La deteccion debe acertar en Datos y NO inventar boilerplate en el resto
    # (en especial Pagos, que con el pico de coste generaba 1381 falsos positivos).
    rows = {r["team"]: r for r in boilerplate_mod.evaluate_detection_all_teams(df)}
    assert rows["Datos"]["precision"] == 1.0
    assert rows["Datos"]["recall"] == 1.0
    for team, r in rows.items():
        if team != "Datos":
            assert r["false_positives"] == 0, team


def test_boilerplate_summary_with_stub(df):
    canned = '{"nombre_patron": "Carga al data lake", "plantilla_sugerida": "...", "automatizable": true, "recomendacion": "automatiza"}'
    stub = StubProvider(lambda p, s: canned)
    report = boilerplate_mod.analyze_team(df, "Datos", provider=stub)
    assert report["clusters"][0]["llm_summary"]["automatizable"] is True


# --- Brief ---
def test_detect_findings_are_deterministic_with_real_numbers(df):
    signals = aggregations.compute_all_signals(df)
    findings = brief_mod.detect_findings(signals, brief_mod.gather_extras(df))
    ids = {f["id"] for f in findings}
    anomaly = next(f for f in findings if f["id"].startswith("anomalia_"))
    assert "EUR" in anomaly["evidencia"] and "x" in anomaly["evidencia"]
    assert "ahorro" in ids and "boilerplate" in ids and "secretos" in ids


# --- Artefacto ---
def test_artifact_anomaly_team_never_recommends_subir(df):
    limits = aggregations.recommended_weekly_limits(df)
    proposal = artifact_mod.build_limit_proposal(
        limits, generated_at="2026-06-23T10:00:00", signed_by="test"
    )
    by_team = {r["equipo"]: r for r in proposal["lineas"]}
    # Pagos tiene anomalia: nunca "subir".
    assert by_team["Pagos"]["accion"] in ("bajar", "optimizar")
    md = artifact_mod.render_markdown(proposal)
    assert "Pagos" in md and "Propuesta de límites" in md


def test_artifact_action_is_deterministic_llm_only_refines_motivo(df):
    limits = aggregations.recommended_weekly_limits(df)
    # El LLM coincide con la regla en Pagos: se usa su prosa para el motivo.
    brief = {
        "recomendaciones_limite": [{"equipo": "Pagos", "accion": "bajar", "motivo": "derroche claro"}],
        "_meta": {"provider": "ollama", "model": "qwen2.5:7b"},
    }
    proposal = artifact_mod.build_limit_proposal(
        limits, generated_at="2026-06-23T10:00:00", signed_by="agente", brief=brief
    )
    pagos = next(r for r in proposal["lineas"] if r["equipo"] == "Pagos")
    assert pagos["accion"] == "bajar"  # deterministico (anomalia activa)
    assert pagos["origen_accion"] == "determinista"  # la accion NUNCA la decide el LLM
    assert pagos["motivo_origen"] == "agente"  # pero el motivo en prosa si, al coincidir


def test_artifact_ignores_llm_action_that_contradicts_rule(df):
    limits = aggregations.recommended_weekly_limits(df)
    # El LLM intenta "subir" en Pagos (que tiene anomalia): se ignora.
    brief = {"recomendaciones_limite": [{"equipo": "Pagos", "accion": "subir", "motivo": "mas presupuesto"}]}
    proposal = artifact_mod.build_limit_proposal(
        limits, generated_at="2026-06-23T10:00:00", signed_by="agente", brief=brief
    )
    pagos = next(r for r in proposal["lineas"] if r["equipo"] == "Pagos")
    assert pagos["accion"] in ("bajar", "optimizar")  # la regla manda, no el LLM
    assert pagos["motivo_origen"] == "determinista"  # no se usa el motivo del LLM contradictorio


# --- Chat ---
def test_chat_answer_with_stub(df):
    signals = aggregations.compute_all_signals(df)

    def responder(prompt: str, system) -> str:
        if system and "enrutador" in system:
            return '{"tool": "coste_por_equipo", "args": {}}'
        return "Pagos es el equipo que mas gasta."

    stub = StubProvider(responder)
    result = chat_mod.answer(stub, signals, df, "que equipo gasta mas")
    assert result["tool"] == "coste_por_equipo"
    assert "Pagos" in result["answer"]
    assert isinstance(result["tool_result"], list)


def test_chat_canonical_team_matching():
    known = ["Pagos", "Core Banking", "Datos"]
    assert chat_mod.canonical_team("pagos", known) == "Pagos"
    assert chat_mod.canonical_team("equipo Pagos", known) == "Pagos"
    assert chat_mod.canonical_team("core banking", known) == "Core Banking"
    assert chat_mod.canonical_team("inexistente", known) is None
    assert chat_mod.canonical_team(None, known) is None


def test_chat_invalid_tool_falls_back(df):
    signals = aggregations.compute_all_signals(df)
    stub = StubProvider(lambda p, s: '{"tool": "inventada", "args": {}}' if "enrutador" in (s or "") else "ok")
    result = chat_mod.answer(stub, signals, df, "lo que sea")
    assert result["tool"] == "coste_por_equipo"  # fallback seguro


def test_numeric_integrity_passes_clean_prose():
    allowed = {84.66, 4.31, 36.9}
    rep = brief_mod.verify_numeric_integrity(["ahorro de 84.66 EUR, ratio x4.31"], allowed)
    assert rep["ok"] is True and rep["invented"] == []


def test_numeric_integrity_flags_invented_number():
    allowed = {84.66}
    rep = brief_mod.verify_numeric_integrity(["el ahorro real es 999.99 EUR"], allowed)
    assert rep["ok"] is False and 999.99 in rep["invented"]


def test_generate_brief_falls_back_when_llm_invents_number(df):
    signals = aggregations.compute_all_signals(df)
    # El LLM mete una cifra que NO esta en los datos: el resumen cae a plantilla.
    prose = {"resumen_ejecutivo": "El ahorro asciende a 999999 EUR este mes.",
             "recomendaciones": []}
    stub = StubProvider(lambda p, s: json.dumps(prose))
    brief = brief_mod.generate_brief(stub, signals, brief_mod.gather_extras(df))
    assert brief["integrity"]["ok"] is False
    assert brief["integrity"].get("fallback_used") is True
    assert "999999" not in brief["resumen_ejecutivo"]  # la cifra inventada no se publica


def test_generate_brief_invented_number_in_recommendation_never_published(df):
    signals = aggregations.compute_all_signals(df)
    # La cifra inventada esta en una RECOMENDACION, no en el resumen: la
    # recomendacion se vacia (no se publica jamas) y el resumen limpio se conserva.
    prose = {"resumen_ejecutivo": "Resumen limpio sin cifras.",
             "recomendaciones": [{"id": "ahorro", "recomendacion": "pasar al barato ahorraria 9999.99 EUR"}]}
    stub = StubProvider(lambda p, s: json.dumps(prose))
    brief = brief_mod.generate_brief(stub, signals, brief_mod.gather_extras(df))
    assert brief["integrity"]["ok"] is False
    assert brief["integrity"].get("fallback_used") is True
    assert "9999.99" not in brief_mod.render_markdown(brief)
    assert brief["resumen_ejecutivo"] == "Resumen limpio sin cifras."


def test_generate_brief_numbers_are_deterministic_not_from_llm(df):
    signals = aggregations.compute_all_signals(df)
    # El LLM SOLO devuelve prosa; las cifras vienen del codigo determinista.
    prose = {"resumen_ejecutivo": "Resumen de prueba.",
             "recomendaciones": [{"id": "ahorro", "recomendacion": "cambiar a modelo barato"}]}
    stub = StubProvider(lambda p, s: json.dumps(prose))
    brief = brief_mod.generate_brief(stub, signals, brief_mod.gather_extras(df))
    assert brief["resumen_ejecutivo"] == "Resumen de prueba."
    assert brief["_meta"]["provider"] == "stub"
    # Recomendaciones de limite deterministas (Pagos baja por anomalia), no del LLM.
    pagos = next(r for r in brief["recomendaciones_limite"] if r["equipo"] == "Pagos")
    assert pagos["accion"] == "bajar"
    # La prosa del LLM se inyecta por id en el hallazgo correcto.
    ahorro = next(f for f in brief["hallazgos"] if f["id"] == "ahorro")
    assert ahorro["recomendacion"] == "cambiar a modelo barato"
    md = brief_mod.render_markdown(brief)
    assert "Brief de gobernanza" in md and "Pagos" in md
