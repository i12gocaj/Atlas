"""Tests del detector de PII estructurada (determinista, con checksum)."""

from __future__ import annotations

from pathlib import Path

from atlas import validation as validation_mod
from atlas.detection import pii


def test_iban_checksum():
    assert pii.iban_valid("ES9121000418450200051332")
    assert pii.iban_valid("DE89370400440532013000")
    # Digitos de control alterados: invalido.
    assert not pii.iban_valid("ES0021000418450200051332")


def test_dni_and_nie_checksum():
    assert pii.dni_valid("12345678Z")
    assert pii.dni_valid("X1234567L")  # NIE
    assert not pii.dni_valid("12345678A")  # letra incorrecta


def test_luhn():
    assert pii.luhn_valid("4111111111111111")
    assert pii.luhn_valid("5500005555555559")
    assert not pii.luhn_valid("4111111111111112")


def test_detect_in_prose():
    f = pii.detect_pii("transfiere a ES9121000418450200051332 para el cliente con DNI 12345678Z")
    types = {x["type"] for x in f}
    assert types == {"iban", "dni"}


def test_value_is_masked():
    f = pii.detect_pii("la cuenta ES9121000418450200051332 del cliente")
    assert f[0]["valor"].startswith("*")
    assert "ES9121000418450200051332" not in f[0]["valor"]


def test_no_false_positives_on_decoys():
    # Numeros con pinta de PII pero checksum invalido o que no son PII.
    assert pii.detect_pii("el pedido 1234 5678 9012 3456 esta pendiente") == []
    assert pii.detect_pii("la cuenta ficticia ES0021000418450200051332 no vale") == []
    assert pii.detect_pii("imputa a la cuenta contable 430000") == []


def test_plain_prose_has_no_pii():
    assert not pii.has_pii("genera los tests del endpoint de pagos con pytest")


def test_gold_set_precision_and_recall():
    rep = validation_mod.evaluate_pii(Path("validation/pii.jsonl"))
    assert rep["herramienta"]["precision"] == 1.0
    assert rep["herramienta"]["recall"] == 1.0
    assert rep["senuelos"]["falsos_positivos"] == 0
    assert rep["errores_de_tipo"] == 0


def test_grouped_iban_no_phantom_card():
    # Un IBAN en formato legible (grupos de 4) no debe generar una tarjeta
    # fantasma a partir de un fragmento de su cuerpo que pase Luhn por azar.
    f = pii.detect_pii("transfiere la nómina a la cuenta ES53 1648 7059 6402 3592 5634 hoy")
    assert [x["type"] for x in f] == ["iban"]


def test_email_with_dni_local_not_double_counted():
    # El DNI que forma la parte local de un email no es un DNI suelto aparte.
    f = pii.detect_pii("avisa a 12345678Z@empresa.com del incidente")
    assert [x["type"] for x in f] == ["email"]


def test_iban_followed_by_amount_is_detected():
    # La regex codiciosa engullia el importe posterior, el checksum fallaba y el
    # IBAN real se descartaba entero (falso negativo en la demo en vivo).
    f = pii.detect_pii("transfiere a ES91 2100 0418 4502 0005 1332 900 euros")
    assert [x["type"] for x in f] == ["iban"]


def test_iban_followed_by_bic_is_detected():
    f = pii.detect_pii("IBAN ES91 2100 0418 4502 0005 1332 BIC CAIXESBB")
    assert [x["type"] for x in f] == ["iban"]


def test_two_ibans_in_a_row_both_detected():
    f = pii.detect_pii(
        "pasa de ES91 2100 0418 4502 0005 1332 a ES79 2100 0813 6101 2345 6789"
    )
    assert [x["type"] for x in f] == ["iban", "iban"]
    assert f[0]["valor"] != f[1]["valor"]


def test_card_followed_by_amount_is_detected():
    f = pii.detect_pii("pago con 4111 1111 1111 1111 100 euros")
    assert [x["type"] for x in f] == ["tarjeta"]


def test_invalid_iban_followed_by_amount_still_discarded():
    # El recorte por la derecha no debe resucitar un senuelo con checksum malo.
    assert pii.detect_pii("la cuenta ES00 2100 0418 4502 0005 1332 900 euros") == []


def test_repeated_email_still_blocks_inner_dni():
    # La segunda ocurrencia de un email debe seguir bloqueando el DNI de su
    # parte local, aunque el hallazgo no se cuente dos veces.
    f = pii.detect_pii("escribe a 12345678Z@banco.es y en copia a 12345678Z@banco.es")
    assert [x["type"] for x in f] == ["email"]
