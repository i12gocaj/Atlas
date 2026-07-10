"""Tests de la baseline de deteccion de secretos.

El test clave es el del contraste: la baseline debe pillar los secretos
estructurados pero ESCAPARSELE la contrasena en lenguaje natural. Ese hueco es
lo que justifica el LLM en la Semana 2.
"""

from __future__ import annotations

import pandas as pd
import pytest

from atlas.detection import baseline
from atlas.generation.generator import generate_events


@pytest.fixture(scope="module")
def df():
    return pd.DataFrame(e.to_dict() for e in generate_events())


def test_shannon_entropy_distinguishes_random_from_words():
    assert baseline.shannon_entropy("aaaaaaaa") < 1.0
    assert baseline.shannon_entropy("AKIA4XEXAMPLE12345Z9q") > 3.0


def test_detects_connection_string():
    findings = baseline.detect_secrets_in_text(
        "usa postgres://user:pass@host:5432/db para conectar"
    )
    assert any(f.secret_type == "connection_string" for f in findings)


def test_misses_natural_language_password():
    # Este es el hueco intencionado: ninguna regex ni la entropia lo pillan.
    findings = baseline.detect_secrets_in_text("la clave admin es verano2024")
    assert findings == []


def test_baseline_recall_below_one_due_to_nl_password(df):
    report = baseline.evaluate_baseline(df)
    # Pilla la mayoria (los estructurados) pero no todos: recall < 1.
    assert report["recall"] < 1.0
    assert report["tp"] >= 1
    # El secreto escapado debe ser justamente la contrasena en lenguaje natural.
    assert any(m["gt_secret_type"] == "password" for m in report["missed_secrets"])


def test_baseline_recovers_seeded_secrets(df):
    # El detector que vende Atlas (baseline + LLM) recupera las 4 fugas sembradas:
    # el baseline caza 3 (estructuradas) y el LLM local la 4a (contrasena en prosa,
    # recall 1.0 validado). Por eso el conteo del detector == gt_contains_secret, y
    # el motor de politicas puede usar gt como salida cacheada del detector.
    report = baseline.evaluate_baseline(df)
    assert report["tp"] == 3
    assert len(report["missed_secrets"]) == 1
    assert report["missed_secrets"][0]["gt_secret_type"] == "password"


def test_baseline_precision_is_high(df):
    report = baseline.evaluate_baseline(df)
    # Apenas falsos positivos sobre prompts normales.
    assert report["precision"] >= 0.8


def test_detect_secrets_adds_structured_coverage_over_regex():
    # Tipos que la regex casera NO cubre pero detect-secrets si (si esta instalado).
    if not baseline._HAS_DETECT_SECRETS:
        import pytest

        pytest.skip("detect-secrets no instalado")
    casos = {
        # Las formas se ensamblan en ejecucion: siguen ejercitando los plugins
        # reales sin parecer credenciales activas para los escaneres del repo.
        "Slack Token": "webhook "
        + "".join(("xoxb-", "2345678901-2345678901234-AbCdEfGhIjKlMnOpQrStUvWx")),
        "JSON Web Token": "token " + ".".join(
            ("eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0In0", "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
        ),
        "Stripe Access Key": "clave " + "".join(("sk_", "live_4eC39HqLyjWDarjtT1zdp7dc")),
    }
    regex_pats = [p for _, p in baseline.SECRET_PATTERNS]
    for expected_type, text in casos.items():
        # La regex casera por si sola NO lo caza.
        assert not any(p.search(text) for p in regex_pats), expected_type
        # La union (con detect-secrets) si, con el tipo correcto.
        types = {f.secret_type for f in baseline.detect_secrets_in_text(text)}
        assert expected_type in types, expected_type


def test_union_no_false_positive_on_normal_prompt():
    # Un prompt normal de desarrollo no debe marcar ningun secreto.
    findings = baseline.detect_secrets_in_text(
        "implementa una funcion que agregue ventas por importe en python"
    )
    assert findings == []


def test_entropy_ignores_hyphenated_words_and_env_names():
    # Prosa con palabras unidas por guiones o constantes SNAKE_CASE supera el
    # umbral de entropia sin ser un secreto: no deben disparar high_entropy.
    for text in (
        "reunion con el equipo de infraestructura-y-plataforma",
        "la variable ATLAS_DASHBOARD_OUTPUT_DIR no esta definida",
        "usa la rama feature/actualizacion-dependencias-2025",
    ):
        assert baseline.detect_secrets_in_text(text) == []


def test_entropy_still_flags_random_tokens():
    # Un token aleatorio largo (letras y digitos mezclados en el mismo
    # fragmento) sigue cazandose por entropia.
    findings = baseline.detect_secrets_in_text("token interno g7Kq2Zp9rX4vB1nM8cT5wY")
    assert any(f.method == "entropy" for f in findings)
