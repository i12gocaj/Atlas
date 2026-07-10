"""Deteccion de secretos y PII con LLM, y su contraste con la baseline.

El detector LLM debe cazar el secreto que la baseline de reglas no pilla: una
contrasena dictada en lenguaje natural ("la clave admin es verano2024"). Ese
delta es uno de los golpes del pitch: lo que solo la IA encuentra.

Para que el analisis de contenido sensible no salga de la maquina, este detector
se debe ejecutar con el proveedor LOCAL (Ollama). La factory ya lo prioriza.
"""

from __future__ import annotations

import pandas as pd

from ..detection import baseline
from ..llm.base import LLMError, LLMProvider
from . import sampling

_SYSTEM = (
    "Eres un detector de seguridad que revisa prompts que los desarrolladores "
    "envian a asistentes de IA. Tu trabajo es detectar si el prompt filtra un "
    "secreto o dato sensible: contrasenas, claves de API, tokens, cadenas de "
    "conexion con credenciales, o PII. Cuenta tambien las contrasenas escritas "
    "en lenguaje natural (por ejemplo 'la clave es ...'). Responde SOLO JSON."
)


def llm_detect_secret(provider: LLMProvider, text: str, *, strict: bool = False) -> dict:
    """Pregunta al LLM si un prompt contiene un secreto. Devuelve dict normalizado.

    Con strict=True, un fallo del LLM se propaga como LLMError en vez de
    devolver "sin secreto": en la demo en vivo, 'modelo no disponible' y 'no
    detecta' son respuestas muy distintas. Los evals mantienen strict=False.
    """
    prompt = (
        f'Analiza este prompt y di si filtra algun secreto o dato sensible.\n\n'
        f'Prompt:\n"""{text}"""\n\n'
        'Devuelve JSON con esta forma exacta: '
        '{"contains_secret": true|false, '
        '"secret_type": "password|api_key|connection_string|pii|null", '
        '"evidence": "<fragmento o breve explicacion>"}'
    )
    try:
        result = provider.generate_json(prompt, system=_SYSTEM)
    except LLMError:
        if strict:
            raise
        return {"contains_secret": False, "secret_type": None, "evidence": ""}
    return {
        "contains_secret": bool(result.get("contains_secret", False)),
        "secret_type": result.get("secret_type") or None,
        "evidence": str(result.get("evidence", ""))[:200],
    }


def _metrics(truth: list[bool], pred: list[bool]) -> dict:
    tp = sum(1 for t, p in zip(truth, pred) if t and p)
    fp = sum(1 for t, p in zip(truth, pred) if not t and p)
    fn = sum(1 for t, p in zip(truth, pred) if t and not p)
    tn = sum(1 for t, p in zip(truth, pred) if not t and not p)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def evaluate_secret_detection(
    provider: LLMProvider,
    df: pd.DataFrame,
    neg_sample: int = 20,
    seed: int = 0,
) -> dict:
    """Evalua LLM contra baseline sobre todos los positivos mas una muestra de negativos.

    Tomamos TODOS los eventos con secreto (son pocos) y una muestra de eventos sin
    secreto. Sobre ese mismo conjunto medimos baseline y LLM, y reportamos el delta
    (lo que el LLM caza y la baseline no).
    """
    positives = df[df["gt_contains_secret"]].copy()
    negatives = sampling.random_sample(df[~df["gt_contains_secret"]], neg_sample, seed)
    eval_set = pd.concat([positives, negatives]).reset_index(drop=True)

    truth = eval_set["gt_contains_secret"].astype(bool).tolist()

    # Baseline (reglas) sobre el mismo conjunto.
    base_pred = (
        eval_set["prompt_text"].map(lambda t: len(baseline.detect_secrets_in_text(t)) > 0).tolist()
    )

    # LLM sobre el mismo conjunto.
    llm_results = [llm_detect_secret(provider, t) for t in eval_set["prompt_text"]]
    llm_pred = [r["contains_secret"] for r in llm_results]

    base_metrics = _metrics(truth, base_pred)
    llm_metrics = _metrics(truth, llm_pred)

    # Lo que el LLM caza y la baseline no (el delta del pitch).
    caught_by_llm_only = []
    for i, ev in eval_set.iterrows():
        if ev["gt_contains_secret"] and llm_pred[i] and not base_pred[i]:
            caught_by_llm_only.append(
                {
                    "team": ev["team"],
                    "user_id": ev["user_id"],
                    "gt_secret_type": ev["gt_secret_type"],
                    "llm_secret_type": llm_results[i]["secret_type"],
                    "evidence": llm_results[i]["evidence"],
                    "prompt_text": ev["prompt_text"][:140],
                }
            )

    return {
        "eval_set_size": len(eval_set),
        "positives": int(len(positives)),
        "negatives": int(len(negatives)),
        "baseline": base_metrics,
        "llm": llm_metrics,
        "caught_by_llm_only": caught_by_llm_only,
    }
