"""Generador del dataset sintetico de uso de IA.

Produce una lista de AIUsageEvent reproducible (misma semilla, mismo dataset).
La unidad de trabajo es la SESION: una tarea que un usuario intenta resolver con
la IA, posiblemente en varios intentos (reintentos encadenados). Esto nos da de
forma natural la senal de "reintentos en cadena" que el analisis aprovecha.

El generador NO sabe de escenarios: delega en `scenarios.py` el perfil semanal
de cada usuario y las inyecciones especiales. Asi el bucle de aqui es simple y
estable, y la complejidad de dominio queda en un solo sitio.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import config
from ..config import ScenarioConfig, SimulationConfig
from ..prompts import corpus
from ..rng import DeterministicRng
from ..schema import AIUsageEvent, compute_cost_eur
from . import scenarios as scn

_MAX_RETRIES = 5


def generate_events(
    sim: SimulationConfig | None = None,
    scenarios: ScenarioConfig | None = None,
) -> list[AIUsageEvent]:
    """Genera el dataset completo de eventos de uso de IA."""
    sim = sim or config.SIMULATION
    scenarios = scenarios or config.SCENARIOS
    base_seed = sim.seed

    events: list[AIUsageEvent] = []

    # Plan de fugas de secretos, indexado por (usuario, semana) para inyectarlas.
    secret_plan = scn.plan_secret_leaks(scenarios, sim, corpus.secret_leak_pool(), base_seed)
    secrets_by_slot: dict[tuple[str, int], list[scn.SecretAssignment]] = {}
    for assignment in secret_plan:
        secrets_by_slot.setdefault((assignment.user, assignment.week_index), []).append(assignment)

    for week_index in range(sim.num_weeks):
        week_start = sim.start_date + timedelta(weeks=week_index)
        for team in config.TEAMS:
            for user in team.users:
                archetype = scn.assign_user_archetype(user, team, base_seed)
                profile = scn.resolve_week_profile(
                    user, team, archetype, week_index, scenarios, sim
                )
                rng = DeterministicRng.for_keys(base_seed, "events", user, week_index)
                events.extend(
                    _generate_user_week(user, team, profile, week_start, sim, rng)
                )

                # Inyectar secretos planificados para este usuario y semana.
                for assignment in secrets_by_slot.get((user, week_index), []):
                    events.append(
                        _build_secret_event(assignment, team, week_start, sim, rng)
                    )

    events.sort(key=lambda e: e.timestamp)
    return events


def _generate_user_week(
    user: str,
    team: config.TeamConfig,
    profile: scn.WeekProfile,
    week_start: datetime | object,
    sim: SimulationConfig,
    rng: DeterministicRng,
) -> list[AIUsageEvent]:
    """Genera todos los eventos de un usuario en una semana, sesion a sesion."""
    out: list[AIUsageEvent] = []
    produced = 0
    target = profile.events_per_week

    while produced < target:
        session_events = _generate_session(user, team, profile, week_start, sim, rng)
        out.extend(session_events)
        produced += len(session_events)

    return out


def _generate_session(
    user: str,
    team: config.TeamConfig,
    profile: scn.WeekProfile,
    week_start,
    sim: SimulationConfig,
    rng: DeterministicRng,
) -> list[AIUsageEvent]:
    """Genera una sesion: primer intento mas posibles reintentos encadenados."""
    session_id = rng.hex_id("ses")
    project = rng.choice(team.projects)
    model = rng.weighted_choice(profile.model_weights)

    # Tipo de sesion: trivial (escenario de coste), boilerplate (escenario Datos)
    # o normal. Se decide por azar segun las fracciones del perfil.
    if profile.trivial_fraction > 0 and rng.chance(profile.trivial_fraction):
        category = config.TRIVIAL_TASK_CATEGORY
        kind = "trivial"
    elif profile.boilerplate_fraction > 0 and rng.chance(profile.boilerplate_fraction):
        category = "codigo"
        kind = "boilerplate"
    else:
        category = rng.choice(config.TASK_CATEGORIES)
        kind = "normal"

    base_time = _sample_session_time(week_start, sim, rng)

    # Numero de reintentos: cadena geometrica gobernada por la propension.
    retries = 0
    while retries < _MAX_RETRIES and rng.chance(profile.retry_propensity):
        retries += 1
    total = 1 + retries

    session: list[AIUsageEvent] = []
    first_id: str | None = None
    for i in range(total):
        is_retry = i > 0
        event_id = rng.hex_id("evt")
        if first_id is None:
            first_id = event_id

        prompt_text, response_summary = _render_text(kind, category, is_retry, rng)
        in_tok, out_tok = _sample_tokens(kind, category, is_retry, sim, rng)
        cost = compute_cost_eur(model, in_tok, out_tok)
        latency = _sample_latency(model, out_tok, rng)

        # Solo el ultimo intento de la sesion puede aceptarse.
        accepted = (i == total - 1) and rng.chance(profile.acceptance_base)

        timestamp = (base_time + timedelta(minutes=4 * i)).isoformat(timespec="seconds")

        session.append(
            AIUsageEvent(
                event_id=event_id,
                session_id=session_id,
                timestamp=timestamp,
                user_id=user,
                team=team.name,
                project=project,
                criticality=team.criticality,
                assistant="ide-copilot",
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_eur=cost,
                latency_ms=latency,
                prompt_text=prompt_text,
                response_summary=response_summary,
                accepted=accepted,
                is_retry=is_retry,
                retry_of=None if not is_retry else first_id,
                gt_task_category=category,
                gt_contains_secret=False,
                gt_secret_type=None,
                # Solo el primer intento es boilerplate; los reintentos son
                # follow-ups genericos ("sigue sin funcionar"), no la plantilla.
                gt_is_boilerplate=(kind == "boilerplate" and not is_retry),
                gt_scenario=_scenario_tag(kind, profile),
            )
        )
    return session


def _build_secret_event(
    assignment: scn.SecretAssignment,
    team: config.TeamConfig,
    week_start,
    sim: SimulationConfig,
    rng: DeterministicRng,
) -> AIUsageEvent:
    """Construye un evento con un secreto plantado (categoria debug)."""
    in_tok = rng.randint(300, 900)
    out_tok = rng.randint(150, 600)
    model = config.MID_MODEL
    cost = compute_cost_eur(model, in_tok, out_tok)
    base_time = _sample_session_time(week_start, sim, rng)
    return AIUsageEvent(
        event_id=rng.hex_id("evt"),
        session_id=rng.hex_id("ses"),
        timestamp=base_time.isoformat(timespec="seconds"),
        user_id=assignment.user,
        team=assignment.team,
        project=assignment.project,
        criticality=team.criticality,
        assistant="ide-copilot",
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_eur=cost,
        latency_ms=_sample_latency(model, out_tok, rng),
        prompt_text=assignment.prompt_text,
        response_summary=assignment.response_summary,
        accepted=rng.chance(0.5),
        is_retry=False,
        retry_of=None,
        gt_task_category="debug",
        gt_contains_secret=True,
        gt_secret_type=assignment.gt_secret_type,
        gt_is_boilerplate=False,
        gt_scenario="secret_leak",
    )


# ---------------------------------------------------------------------------
# Muestreo de detalles (texto, tokens, latencia, tiempo)
# ---------------------------------------------------------------------------
def _render_text(kind: str, category: str, is_retry: bool, rng: DeterministicRng):
    if is_retry:
        return corpus.render_retry_followup(rng), corpus.render_response(category, rng)
    if kind == "trivial":
        return corpus.render_trivial(rng)
    if kind == "boilerplate":
        return corpus.render_boilerplate(rng)
    # normal: el arquetipo lo decide corpus segun el azar (senior/junior/mixed).
    archetype = "mixed"
    return corpus.render_prompt(category, archetype, rng), corpus.render_response(category, rng)


def _sample_tokens(kind: str, category: str, is_retry: bool, sim: SimulationConfig, rng):
    if kind == "trivial":
        min_in, max_in, min_out, max_out = sim.trivial_token_range
    else:
        min_in, max_in, min_out, max_out = sim.token_ranges[category]
    in_tok = rng.randint(min_in, max_in)
    out_tok = rng.randint(min_out, max_out)
    if is_retry:
        # Los reintentos suelen ser mas cortos en la entrada.
        in_tok = int(in_tok * 0.6)
    return in_tok, out_tok


def _sample_latency(model: str, output_tokens: int, rng: DeterministicRng) -> int:
    base = config.MODELS[model].latency_ms_per_1k_output * (output_tokens / 1000.0)
    noise = rng.randint(-80, 200)
    return max(50, int(base + noise))


def _sample_session_time(week_start, sim: SimulationConfig, rng: DeterministicRng) -> datetime:
    """Elige un instante en horario laboral dentro de la semana."""
    weekday = rng.randint(0, sim.working_days_per_week - 1)
    hour = rng.randint(sim.work_hour_start, sim.work_hour_end - 1)
    minute = rng.randint(0, 59)
    day = week_start + timedelta(days=weekday)
    return datetime(day.year, day.month, day.day, hour, minute)


def _scenario_tag(kind: str, profile: scn.WeekProfile) -> str | None:
    # Durante el pico, todos los eventos de la semana son parte del escenario.
    if profile.scenario == "cost_spike":
        return "cost_spike"
    if kind == "boilerplate":
        return "boilerplate"
    return profile.scenario if profile.scenario == "low_acceptance" else None
