"""Utilidades de aleatoriedad determinista.

Todo el azar del generador pasa por aqui, con una semilla fija, para que el
dataset sea 100% reproducible: misma semilla, mismo dataset, byte a byte. Eso
hace la demo estable y los tests fiables.

Nunca usamos el modulo global `random` ni la hora del sistema para nada que
acabe en el dataset.
"""

from __future__ import annotations

import random
from typing import Sequence, TypeVar

T = TypeVar("T")


class DeterministicRng:
    """Envoltura fina sobre random.Random con helpers comodos y deterministas."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    @classmethod
    def for_keys(cls, base_seed: int, *parts: object) -> "DeterministicRng":
        """Construye un RNG estable a partir de una semilla base y unas claves.

        A diferencia de `derive`, no depende del estado interno: la misma
        (base_seed, parts) da siempre el mismo RNG. Es el metodo preferido para
        aislar la secuencia de cada usuario y semana.
        """
        key = "|".join(str(p) for p in parts)
        # hash() de un str varia entre procesos, por eso usamos un hash estable.
        child_seed = (base_seed ^ _stable_hash(key)) & 0xFFFFFFFF
        return cls(child_seed)

    # --- helpers ---
    def random(self) -> float:
        """Float en [0, 1)."""
        return self._rng.random()

    def randint(self, low: int, high: int) -> int:
        """Entero en [low, high] (ambos inclusive)."""
        return self._rng.randint(low, high)

    def choice(self, seq: Sequence[T]) -> T:
        """Elige un elemento al azar de una secuencia no vacia."""
        return self._rng.choice(seq)

    def weighted_choice(self, options: dict[T, float]) -> T:
        """Elige una clave segun sus pesos relativos (no hace falta normalizar)."""
        keys = list(options.keys())
        weights = list(options.values())
        return self._rng.choices(keys, weights=weights, k=1)[0]

    def shuffle(self, items: list[T]) -> list[T]:
        """Devuelve una copia barajada de la lista."""
        copy = list(items)
        self._rng.shuffle(copy)
        return copy

    def chance(self, probability: float) -> bool:
        """True con la probabilidad dada (0 a 1)."""
        return self._rng.random() < probability

    def hex_id(self, prefix: str, bits: int = 48) -> str:
        """Genera un id hexadecimal determinista con prefijo."""
        return f"{prefix}_{self._rng.getrandbits(bits):0{bits // 4}x}"


def _stable_hash(text: str) -> int:
    """Hash entero estable entre procesos (FNV-1a de 32 bits)."""
    h = 0x811C9DC5
    for ch in text.encode("utf-8"):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h
