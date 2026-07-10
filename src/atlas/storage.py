"""Persistencia de eventos y señales.

Formato principal: JSONL (un evento JSON por linea). Es facil de inspeccionar a
ojo, no necesita dependencias y se versiona razonablemente. Para las señales
exportamos CSV (comodo para hojas de calculo y para el dashboard).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import AIUsageEvent


def write_events_jsonl(events: Iterable[AIUsageEvent], path: str | Path) -> int:
    """Escribe eventos en formato JSONL. Devuelve cuantos escribio."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(event.to_json_line())
            fh.write("\n")
            count += 1
    return count


def read_events_jsonl(path: str | Path) -> list[AIUsageEvent]:
    """Lee eventos desde un fichero JSONL."""
    path = Path(path)
    events: list[AIUsageEvent] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            events.append(AIUsageEvent.from_dict(json.loads(line)))
    return events


def read_events_raw(path: str | Path) -> list[dict]:
    """Lee los eventos como diccionarios planos (sin construir dataclasses).

    Util para cargar directamente en pandas sin coste de validacion.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el fichero de eventos: {path}. Genera el dataset con "
            "'python -m atlas.cli generate'."
        )
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
