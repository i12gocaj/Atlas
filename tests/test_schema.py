"""Tests del esquema y del calculo de coste."""

from __future__ import annotations

import pytest

from atlas.schema import AIUsageEvent, compute_cost_eur


def _valid_event(**overrides):
    base = dict(
        event_id="evt_1",
        session_id="ses_1",
        timestamp="2026-04-06T09:30:00",
        user_id="ana.ruiz",
        team="Pagos",
        project="pasarela-pagos",
        criticality="alta",
        assistant="ide-copilot",
        model="balanced",
        input_tokens=1000,
        output_tokens=500,
        cost_eur=compute_cost_eur("balanced", 1000, 500),
        latency_ms=300,
        prompt_text="hola",
        response_summary="ok",
        accepted=True,
        is_retry=False,
        retry_of=None,
        gt_task_category="codigo",
        gt_contains_secret=False,
        gt_secret_type=None,
        gt_is_boilerplate=False,
        gt_scenario=None,
    )
    base.update(overrides)
    return AIUsageEvent(**base)


def test_cost_is_deterministic_and_correct():
    # balanced: 0.03/1k input, 0.09/1k output.
    assert compute_cost_eur("balanced", 1000, 500) == round(0.03 + 0.045, 4)


def test_roundtrip_serialization():
    event = _valid_event()
    restored = AIUsageEvent.from_dict(event.to_dict())
    assert restored == event


def test_invalid_model_raises():
    with pytest.raises(ValueError):
        _valid_event(model="inexistente")


def test_retry_without_parent_raises():
    with pytest.raises(ValueError):
        _valid_event(is_retry=True, retry_of=None)


def test_secret_without_type_raises():
    with pytest.raises(ValueError):
        _valid_event(gt_contains_secret=True, gt_secret_type=None)
