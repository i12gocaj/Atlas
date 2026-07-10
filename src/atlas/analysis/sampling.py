"""Muestreo reproducible para las evaluaciones con LLM.

Evaluar con un LLM local tiene coste (segundos por llamada), asi que validamos
sobre muestras. El muestreo es determinista (random_state fijo) y, cuando hace
falta, estratificado, para que la evaluacion cubra todas las categorias y sea
honesta y repetible.
"""

from __future__ import annotations

import pandas as pd


def stratified_sample(
    df: pd.DataFrame, by: str, per_group: int, seed: int = 0
) -> pd.DataFrame:
    """Toma hasta `per_group` filas de cada grupo de `by`, de forma determinista."""
    parts = []
    for _, group in df.groupby(by):
        n = min(per_group, len(group))
        parts.append(group.sample(n=n, random_state=seed))
    return pd.concat(parts).reset_index(drop=True)


def random_sample(df: pd.DataFrame, n: int, seed: int = 0) -> pd.DataFrame:
    """Muestra aleatoria determinista de hasta n filas."""
    n = min(n, len(df))
    return df.sample(n=n, random_state=seed).reset_index(drop=True)
