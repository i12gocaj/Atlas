"""Escenarios sembrados a proposito.

Aqui vive TODA la logica que hace que el dataset tenga senales descubribles.
Mantenerla centralizada y separada del bucle de generacion tiene dos ventajas:
es facil de auditar (que estamos plantando y donde) y es facil anadir o quitar
escenarios sin tocar el generador.

Cada escenario se expresa como un ajuste sobre el "perfil semanal" de un usuario
o como una inyeccion de eventos especiales (los secretos plantados).
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from ..config import ScenarioConfig, SimulationConfig, TeamConfig
from ..rng import DeterministicRng


@dataclass
class WeekProfile:
    """Mandos que gobiernan como un usuario usa la IA en una semana concreta."""

    archetype: str
    events_per_week: int
    model_weights: dict[str, float]
    acceptance_base: float
    retry_propensity: float
    boilerplate_fraction: float = 0.0
    trivial_fraction: float = 0.0  # parte de autocompletado trivial (escenario de coste)
    scenario: str | None = None  # etiqueta del escenario activo, o None


def assign_user_archetype(user: str, team: TeamConfig, base_seed: int) -> str:
    """Asigna a cada usuario un arquetipo fijo y determinista.

    El arquetipo no cambia entre semanas: una persona es coherente consigo misma.
    """
    rng = DeterministicRng.for_keys(base_seed, "archetype", team.name, user)
    return rng.weighted_choice(team.archetype_mix)


def resolve_week_profile(
    user: str,
    team: TeamConfig,
    archetype: str,
    week_index: int,
    scenarios: ScenarioConfig,
    sim: SimulationConfig,
) -> WeekProfile:
    """Calcula el perfil de uso de un usuario en una semana, aplicando escenarios."""
    arch = config.ARCHETYPES[archetype]
    profile = WeekProfile(
        archetype=archetype,
        events_per_week=arch.events_per_week,
        model_weights=dict(arch.model_weights),
        acceptance_base=arch.acceptance_base,
        retry_propensity=arch.retry_propensity,
    )

    # Escenario 1: pico de coste en Pagos a partir de cierta semana. El equipo
    # pasa al modelo caro para todo y dispara el volumen, con buena parte en
    # autocompletado trivial (modelo caro malgastado en tareas que no lo merecen).
    if team.name == scenarios.cost_spike_team and week_index >= scenarios.cost_spike_start_week:
        profile.events_per_week = int(round(profile.events_per_week * scenarios.cost_spike_events_multiplier))
        profile.model_weights = {scenarios.cost_spike_model: 1.0}
        profile.trivial_fraction = scenarios.cost_spike_trivial_fraction
        profile.scenario = "cost_spike"

    # Escenario 2: boilerplate repetido en Datos.
    if team.name == scenarios.boilerplate_team:
        profile.boilerplate_fraction = scenarios.boilerplate_fraction

    # Escenario 4: baja adopcion en Equipo Nuevo.
    if team.name == scenarios.low_acceptance_team:
        profile.acceptance_base = max(0.05, profile.acceptance_base - scenarios.low_acceptance_penalty)
        profile.scenario = profile.scenario or "low_acceptance"

    return profile


@dataclass
class SecretAssignment:
    """Una fuga de secreto plantada: a quien, en que semana y con que contenido."""

    user: str
    team: str
    project: str
    week_index: int
    prompt_text: str
    response_summary: str
    gt_secret_type: str


def plan_secret_leaks(
    scenarios: ScenarioConfig,
    sim: SimulationConfig,
    secret_pool: list[dict[str, str]],
    base_seed: int,
) -> list[SecretAssignment]:
    """Decide donde se plantan las fugas de secretos (equipo Plataforma).

    Distribuye `secret_leak_count` secretos entre los usuarios y semanas del
    equipo objetivo, de forma determinista. Devolver esto como plan explicito
    permite validar despues, sin ambiguedad, cuantos secretos hay y donde.
    """
    team = config.team_by_name(scenarios.secret_leak_team)
    rng = DeterministicRng.for_keys(base_seed, "secret_leaks")
    assignments: list[SecretAssignment] = []
    count = min(scenarios.secret_leak_count, len(secret_pool))
    for i in range(count):
        leak = secret_pool[i]
        user = rng.choice(team.users)
        project = rng.choice(team.projects)
        week_index = rng.randint(0, sim.num_weeks - 1)
        assignments.append(
            SecretAssignment(
                user=user,
                team=team.name,
                project=project,
                week_index=week_index,
                prompt_text=leak["prompt_text"],
                response_summary=leak["response_summary"],
                gt_secret_type=leak["gt_secret_type"],
            )
        )
    return assignments
