"""Configuracion central de Atlas.

Esta es la unica fuente de verdad para los parametros del dominio: equipos,
modelos y sus tarifas, categorias de tarea, arquetipos de usuario y los
parametros de la simulacion (incluidos los escenarios sembrados a proposito).

Regla de diseno: aqui NO hay logica, solo datos. Cualquier numero que quieras
ajustar para la demo (precios, frecuencias, intensidad del pico de coste) se
toca aqui y se propaga al resto del sistema. Asi es facil de auditar y de tunear
sin tocar el codigo de generacion.

Todos los importes estan en euros (EUR). Las tarifas son EUR por cada 1.000
tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# ---------------------------------------------------------------------------
# Categorias de tarea
# ---------------------------------------------------------------------------
# Son las categorias "reales" (ground truth) de cada interaccion. En produccion
# NO se observan: el clasificador LLM de la Semana 2 las predice a partir del
# texto del prompt. Aqui las conocemos solo para validar ese clasificador.
TASK_CATEGORIES: tuple[str, ...] = (
    "codigo",
    "documentacion",
    "pruebas",
    "requisitos",
    "debug",
    "analisis",
)

# Categoria especial usada por el escenario del pico de coste: autocompletado
# trivial. Cuenta como "codigo" a efectos de ground truth, pero la marcamos
# aparte para poder demostrar el uso de modelo caro en tareas que no lo merecen.
TRIVIAL_TASK_CATEGORY = "codigo"


# ---------------------------------------------------------------------------
# Modelos y tarifas
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ModelTariff:
    """Tarifa de un modelo de IA, en EUR por 1.000 tokens."""

    name: str
    price_per_1k_input: float
    price_per_1k_output: float
    tier: str  # "barato", "medio" o "caro"
    latency_ms_per_1k_output: float  # base de latencia, para realismo


MODELS: dict[str, ModelTariff] = {
    "swift": ModelTariff("swift", 0.010, 0.030, "barato", 220.0),
    "balanced": ModelTariff("balanced", 0.030, 0.090, "medio", 380.0),
    "deep": ModelTariff("deep", 0.090, 0.240, "caro", 650.0),
}

CHEAP_MODEL = "swift"
MID_MODEL = "balanced"
EXPENSIVE_MODEL = "deep"


# ---------------------------------------------------------------------------
# Arquetipos de usuario
# ---------------------------------------------------------------------------
# Describen COMO le habla cada persona a la IA. Es la base del valor de Atlas:
# distinguir quien usa bien la IA de quien la usa mal y caro.
@dataclass(frozen=True)
class Archetype:
    """Perfil de comportamiento de un usuario frente a la IA."""

    name: str
    # Propension a encadenar reintentos en una misma tarea (0 a 1).
    retry_propensity: float
    # Numero medio de eventos por semana y persona.
    events_per_week: int
    # Probabilidad base de que la sugerencia final sea aceptada (0 a 1).
    acceptance_base: float
    # Pesos relativos de uso de cada modelo (no hace falta que sumen 1).
    model_weights: dict[str, float]


ARCHETYPES: dict[str, Archetype] = {
    # Prompts ricos, pocas iteraciones, alta aceptacion, modelo ajustado a la tarea.
    "senior_prompter": Archetype(
        name="senior_prompter",
        retry_propensity=0.15,
        events_per_week=28,
        acceptance_base=0.82,
        model_weights={"swift": 0.45, "balanced": 0.45, "deep": 0.10},
    ),
    # Prompts vagos, muchos reintentos, baja aceptacion, abusa del modelo caro.
    "junior_prompter": Archetype(
        name="junior_prompter",
        retry_propensity=0.55,
        events_per_week=42,
        acceptance_base=0.45,
        model_weights={"swift": 0.20, "balanced": 0.40, "deep": 0.40},
    ),
    # Perfil intermedio.
    "mixed": Archetype(
        name="mixed",
        retry_propensity=0.32,
        events_per_week=34,
        acceptance_base=0.63,
        model_weights={"swift": 0.30, "balanced": 0.50, "deep": 0.20},
    ),
}


# ---------------------------------------------------------------------------
# Criticidad de proyecto
# ---------------------------------------------------------------------------
CRITICALITY_LEVELS: tuple[str, ...] = ("alta", "media", "baja")


# ---------------------------------------------------------------------------
# Equipos y usuarios
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TeamConfig:
    """Configuracion de un equipo de la organizacion simulada."""

    name: str
    criticality: str
    projects: tuple[str, ...]
    users: tuple[str, ...]
    # Mezcla de arquetipos del equipo: arquetipo -> peso.
    archetype_mix: dict[str, float]


TEAMS: tuple[TeamConfig, ...] = (
    TeamConfig(
        name="Pagos",
        criticality="alta",
        projects=("pasarela-pagos", "conciliacion"),
        users=("ana.ruiz", "luis.gomez", "marta.diaz", "pedro.sanz"),
        archetype_mix={"senior_prompter": 0.25, "mixed": 0.5, "junior_prompter": 0.25},
    ),
    TeamConfig(
        name="Core Banking",
        criticality="alta",
        projects=("ledger", "cuentas"),
        users=("sofia.leon", "javier.mora", "elena.vega"),
        archetype_mix={"senior_prompter": 0.5, "mixed": 0.4, "junior_prompter": 0.1},
    ),
    TeamConfig(
        name="Plataforma",
        criticality="media",
        projects=("infra-core", "observabilidad"),
        users=("diego.romero", "clara.nunez", "hugo.prieto"),
        archetype_mix={"senior_prompter": 0.6, "mixed": 0.35, "junior_prompter": 0.05},
    ),
    TeamConfig(
        name="Datos",
        criticality="media",
        projects=("data-lake", "reporting"),
        users=("nuria.cano", "ivan.soto", "laura.gil", "raul.mesa"),
        archetype_mix={"senior_prompter": 0.3, "mixed": 0.5, "junior_prompter": 0.2},
    ),
    TeamConfig(
        name="Equipo Nuevo",
        criticality="baja",
        projects=("onboarding-app",),
        users=("alex.crespo", "berta.lima", "noa.fuentes"),
        archetype_mix={"senior_prompter": 0.1, "mixed": 0.4, "junior_prompter": 0.5},
    ),
)


# ---------------------------------------------------------------------------
# Escenarios sembrados a proposito
# ---------------------------------------------------------------------------
# Estas son las "verdades" que el agente de la Semana 2 debe ser capaz de
# descubrir. Las plantamos de forma controlada para que la demo no dependa de
# la suerte, y luego validamos honestamente que los detectores las encuentran.
@dataclass(frozen=True)
class ScenarioConfig:
    """Parametros de los cuatro escenarios sembrados."""

    # 1) Pico de coste en Pagos a partir de una semana: el equipo pasa al modelo
    #    caro para todo y dispara el volumen de autocompletado trivial. El coste
    #    se multiplica por el desajuste (modelo caro en tareas que no lo merecen)
    #    mas el volumen.
    cost_spike_team: str = "Pagos"
    cost_spike_start_week: int = 3  # indice de semana (0-based) en que empieza
    cost_spike_events_multiplier: float = 4.0  # mas volumen de interacciones
    cost_spike_trivial_fraction: float = 0.6  # parte que es autocompletado trivial
    cost_spike_model: str = EXPENSIVE_MODEL

    # 2) Boilerplate repetido en Datos: fraccion de SESIONES cuyo primer intento
    #    es la misma plantilla reformulada (los reintentos no se marcan, asi que
    #    equivale a ~37% de los primeros intentos y ~20% de los eventos del
    #    equipo). Candidata a automatizar.
    boilerplate_team: str = "Datos"
    boilerplate_fraction: float = 0.40

    # 3) Fugas de secretos en Plataforma: numero de prompts con secreto plantado.
    secret_leak_team: str = "Plataforma"
    secret_leak_count: int = 4

    # 4) Baja adopcion en Equipo Nuevo: penalizacion sobre la aceptacion base.
    low_acceptance_team: str = "Equipo Nuevo"
    low_acceptance_penalty: float = 0.20  # se resta a acceptance_base


SCENARIOS = ScenarioConfig()


# ---------------------------------------------------------------------------
# Parametros globales de la simulacion
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SimulationConfig:
    """Parametros globales del generador de dataset sintetico."""

    seed: int = 42
    # Fecha de inicio anclada (un lunes) para reproducibilidad. No usamos
    # la fecha actual a proposito: el dataset debe ser identico en cada ejecucion.
    start_date: date = date(2026, 4, 6)
    num_weeks: int = 8
    working_days_per_week: int = 5
    work_hour_start: int = 8
    work_hour_end: int = 19

    # Rangos de tokens por categoria de tarea: (min_in, max_in, min_out, max_out).
    token_ranges: dict[str, tuple[int, int, int, int]] = field(
        default_factory=lambda: {
            "codigo": (800, 2500, 300, 1500),
            "documentacion": (400, 1500, 600, 2500),
            "pruebas": (600, 1800, 400, 1400),
            "requisitos": (300, 1200, 400, 1800),
            "debug": (500, 2000, 200, 1200),
            "analisis": (500, 1800, 500, 2000),
        }
    )
    # Tokens del autocompletado trivial (pequenos, pero muy frecuentes).
    trivial_token_range: tuple[int, int, int, int] = (80, 400, 40, 300)


SIMULATION = SimulationConfig()


# ---------------------------------------------------------------------------
# Helpers de solo lectura sobre la configuracion
# ---------------------------------------------------------------------------
def all_users() -> list[tuple[str, TeamConfig]]:
    """Devuelve la lista de (user_id, equipo) de toda la organizacion."""
    pairs: list[tuple[str, TeamConfig]] = []
    for team in TEAMS:
        for user in team.users:
            pairs.append((user, team))
    return pairs


def team_by_name(name: str) -> TeamConfig:
    """Devuelve la configuracion de un equipo por su nombre."""
    for team in TEAMS:
        if team.name == name:
            return team
    raise KeyError(f"Equipo desconocido: {name}")
