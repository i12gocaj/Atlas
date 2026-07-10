"""Clasificacion de la categoria de tarea desde el texto del prompt.

Dos clasificadores y un evaluador que los enfrenta:

- rule_classify: baseline por palabras clave. Barata y fragil. Se hunde con
  prompts vagos o ambiguos.
- llm_classify: usa el modelo. Entiende intencion y contexto.

El evaluador mide la accuracy de ambos contra la categoria real (gt_task_category)
sobre una muestra. Ese contraste reglas contra IA es uno de los momentos del pitch:
demuestra, con numeros, que la IA no esta de adorno.
"""

from __future__ import annotations

import pandas as pd

from .. import config
from ..llm.base import LLMError, LLMProvider
from . import sampling

VALID_CATEGORIES = set(config.TASK_CATEGORIES)

# Reglas por palabras clave, en orden de prioridad (la primera que casa, gana).
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("debug", ("error", "falla", "no funciona", "peta", "stacktrace", "bug", "excepcion", "arregla")),
    ("pruebas", ("test", "prueba", "pytest", "unitaria", "uat", "cobertura")),
    ("documentacion", ("documenta", " doc", "readme", "guia", "documentacion")),
    ("requisitos", ("requisito", "historia de usuario", "criterios de aceptacion", "necesito para")),
    ("analisis", ("analiza", "compara", "patron", "evolucion", "tendencia", "que pasa con")),
    ("codigo", ("implementa", "funcion", "endpoint", "codigo", "script", "como saco")),
]

_SYSTEM = (
    "Eres un clasificador preciso de prompts de desarrollo de software y datos. "
    "Dada la interaccion de un desarrollador con un asistente de IA, decide la "
    "categoria de tarea. Responde SOLO con JSON valido."
)

_CATEGORY_GUIDE = (
    "codigo: pide escribir o modificar codigo (funciones, endpoints, scripts). "
    "documentacion: pide documentar procesos, tablas o guias. "
    "pruebas: pide tests unitarios, de integracion o UAT. "
    "requisitos: pide extraer requisitos o criterios de aceptacion. "
    "debug: pide encontrar o arreglar un error o fallo. "
    "analisis: pide analizar datos, comparar o explicar patrones."
)


def rule_classify(text: str) -> str:
    """Clasifica por palabras clave. Devuelve 'codigo' por defecto."""
    low = (text or "").lower()
    for category, keywords in _RULES:
        if any(kw in low for kw in keywords):
            return category
    return "codigo"


def llm_classify(provider: LLMProvider, text: str) -> str:
    """Clasifica usando el LLM. Devuelve una categoria valida o 'desconocida'."""
    prompt = (
        f"Categorias y su significado:\n{_CATEGORY_GUIDE}\n\n"
        f'Prompt del desarrollador:\n"""{text}"""\n\n'
        'Devuelve JSON exactamente con esta forma: {"category": "<una categoria>"}'
    )
    try:
        result = provider.generate_json(prompt, system=_SYSTEM)
    except LLMError:
        return "desconocida"
    category = str(result.get("category", "")).strip().lower()
    return category if category in VALID_CATEGORIES else "desconocida"


def evaluate_classifiers(
    provider: LLMProvider,
    df: pd.DataFrame,
    per_category: int = 3,
    seed: int = 0,
) -> dict:
    """Enfrenta reglas contra LLM sobre una muestra estratificada por categoria real.

    Devuelve accuracy de cada enfoque y el detalle por ejemplo, para poder
    ensenar en la demo donde fallan las reglas y acierta el LLM.
    """
    sample = sampling.stratified_sample(df, "gt_task_category", per_category, seed)
    rows = []
    rule_ok = 0
    llm_ok = 0
    for _, ev in sample.iterrows():
        truth = ev["gt_task_category"]
        rule_pred = rule_classify(ev["prompt_text"])
        llm_pred = llm_classify(provider, ev["prompt_text"])
        rule_hit = rule_pred == truth
        llm_hit = llm_pred == truth
        rule_ok += int(rule_hit)
        llm_ok += int(llm_hit)
        rows.append(
            {
                "prompt_text": ev["prompt_text"][:120],
                "truth": truth,
                "rule_pred": rule_pred,
                "llm_pred": llm_pred,
                "rule_hit": rule_hit,
                "llm_hit": llm_hit,
            }
        )
    n = len(sample)
    return {
        "n": n,
        "rule_accuracy": round(rule_ok / n, 3) if n else 0.0,
        "llm_accuracy": round(llm_ok / n, 3) if n else 0.0,
        "rule_correct": rule_ok,
        "llm_correct": llm_ok,
        "details": rows,
    }
