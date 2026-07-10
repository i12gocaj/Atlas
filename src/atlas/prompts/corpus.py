"""Construccion determinista del corpus de prompts y respuestas.

Esta capa aisla COMO se produce el texto. Hoy combina las plantillas de
`templates.py` rellenando placeholders con vocabulario. Si manana quieres un
corpus generado por un LLM y congelado, basta con reemplazar la implementacion
de `render_prompt` / `render_response` sin tocar el generador de eventos.
"""

from __future__ import annotations

import re

from ..rng import DeterministicRng
from . import templates

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _fill(text: str, rng: DeterministicRng) -> str:
    """Rellena los placeholders {x} con vocabulario, de forma determinista."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        options = templates.VOCAB.get(key)
        if not options:
            return match.group(0)
        return rng.choice(options)

    return _PLACEHOLDER.sub(repl, text)


def render_prompt(category: str, archetype: str, rng: DeterministicRng) -> str:
    """Devuelve un prompt realista para una categoria y arquetipo dados."""
    pool = templates.SENIOR_PROMPTS if archetype == "senior_prompter" else templates.JUNIOR_PROMPTS
    # 'mixed' usa senior o junior segun el azar, para reflejar variabilidad real.
    if archetype == "mixed":
        pool = templates.SENIOR_PROMPTS if rng.chance(0.6) else templates.JUNIOR_PROMPTS
    template = rng.choice(pool[category])
    return _fill(template, rng)


def render_response(category: str, rng: DeterministicRng) -> str:
    """Devuelve un resumen de respuesta realista para una categoria."""
    return _fill(rng.choice(templates.RESPONSE_SUMMARIES[category]), rng)


def render_retry_followup(rng: DeterministicRng) -> str:
    """Devuelve un follow-up corto para un evento de reintento."""
    return rng.choice(templates.RETRY_FOLLOWUPS)


def render_trivial(rng: DeterministicRng) -> tuple[str, str]:
    """Devuelve (prompt, respuesta) de un autocompletado trivial."""
    return rng.choice(templates.TRIVIAL_PROMPTS), templates.TRIVIAL_RESPONSE


def render_boilerplate(rng: DeterministicRng) -> tuple[str, str]:
    """Devuelve (prompt, respuesta) del cluster de boilerplate repetido."""
    prompt = _fill(rng.choice(templates.BOILERPLATE_VARIANTS), rng)
    return prompt, templates.BOILERPLATE_RESPONSE


def secret_leak_pool() -> list[dict[str, str]]:
    """Devuelve los prompts con secreto plantado (sin azar, son fijos)."""
    return list(templates.SECRET_LEAK_PROMPTS)
