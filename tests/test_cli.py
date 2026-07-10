"""Tests de seguridad y compatibilidad de la interfaz de linea de comandos."""

from __future__ import annotations

import io

from atlas import cli
from atlas.analysis import secrets_llm
from atlas.llm.base import LLMError


def _stub_scan_model(monkeypatch, result):
    monkeypatch.setattr(cli, "get_provider", lambda: object())
    monkeypatch.setattr(secrets_llm, "llm_detect_secret", lambda *args, **kwargs: result)


def test_scan_reads_stdin_without_echoing_input_or_llm_evidence(monkeypatch, capsys):
    sensitive = "la clave es SuperSecret2026 y el IBAN es ES9121000418450200051332"
    evidence = "SuperSecret2026"
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(sensitive))
    _stub_scan_model(
        monkeypatch,
        {"contains_secret": True, "secret_type": "password", "evidence": evidence},
    )

    cli.main(["scan"])

    output = capsys.readouterr().out
    assert sensitive not in output
    assert "SuperSecret2026" not in output
    assert "****1332" in output
    assert "secreto detectado: password" in output


def test_scan_keeps_positional_input_compatible_and_redacted(monkeypatch, capsys):
    sensitive = "token interno g7Kq2Zp9rX4vB1nM8cT5wY"
    _stub_scan_model(
        monkeypatch,
        {"contains_secret": False, "secret_type": None, "evidence": ""},
    )

    cli.main(["scan", sensitive])

    output = capsys.readouterr().out
    assert sensitive not in output
    assert "Entrada analizada:" in output
    assert "high_entropy" in output


def test_scan_does_not_echo_sensitive_llm_error(monkeypatch, capsys):
    sensitive = "la clave es SuperSecret2026"
    monkeypatch.setattr(cli, "get_provider", lambda: object())

    def fail(*args, **kwargs):
        raise LLMError(f"respuesta invalida: {sensitive}")

    monkeypatch.setattr(secrets_llm, "llm_detect_secret", fail)

    cli.main(["scan", sensitive])

    output = capsys.readouterr().out
    assert sensitive not in output
    assert "SuperSecret2026" not in output
    assert "modelo no disponible" in output
