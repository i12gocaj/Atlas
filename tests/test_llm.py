"""Tests de la capa LLM: parseo robusto, stub y factory."""

from __future__ import annotations

import pytest

from atlas.llm import StubProvider, extract_json
from atlas.llm.base import LLMError
from atlas.llm.config import LLMSettings
from atlas.llm.factory import get_provider


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_surrounding_text():
    assert extract_json('Claro, aqui tienes: {"category": "debug"} fin') == {"category": "debug"}


def test_extract_json_invalid_raises():
    with pytest.raises(LLMError):
        extract_json("no hay json aqui")


def test_stub_provider_records_calls():
    stub = StubProvider(lambda prompt, system: '{"ok": true}')
    out = stub.generate_json("hola", system="sys")
    assert out == {"ok": True}
    assert stub.calls and stub.calls[0]["system"] == "sys"


def test_factory_raises_when_ollama_unavailable():
    settings = LLMSettings(
        ollama_model="x",
        ollama_host="http://127.0.0.1:1",  # puerto muerto, Ollama no responde
    )
    with pytest.raises(LLMError):
        get_provider(settings)


def test_extract_json_array_degrades_to_llmerror():
    # Un array JSON valido no es un objeto: debe degradar como LLMError (los
    # llamadores ya tienen fallback), nunca reventar luego con .get().
    with pytest.raises(LLMError):
        extract_json("[1, 2, 3]")


def test_extract_json_array_with_single_object_rescues_it():
    # Caso tipico de modelo pequeno: envuelve el objeto en un array.
    assert extract_json('[{"tool": "ahorro"}]') == {"tool": "ahorro"}
