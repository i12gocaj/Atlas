"""Benchmark de modelos locales para las tareas de Atlas.

Enfrenta varios modelos de Ollama en las dos tareas de analisis que mas importan
(clasificacion de tareas y deteccion de secretos), sobre la misma muestra, y
mide acierto y latencia. Sirve para decidir, con datos, que modelo local usar.

Uso:
  PYTHONPATH=src python scripts/benchmark_models.py
"""

from __future__ import annotations

import time

import pandas as pd

from atlas.analysis import classifier, secrets_llm
from atlas.llm.ollama_provider import OllamaProvider
from atlas.signals import aggregations

MODELS = ["phi4:14b", "qwen2.5:7b", "llama3.2:3b"]
EVENTS = "data/events.jsonl"
PER_CATEGORY = 2
NEG_SAMPLE = 4


def main() -> None:
    df = aggregations.load_dataframe(EVENTS)
    results = []
    for model in MODELS:
        provider = OllamaProvider(model)
        print(f"\n=== {model} ===")

        t0 = time.time()
        clf = classifier.evaluate_classifiers(provider, df, per_category=PER_CATEGORY, seed=0)
        t_clf = time.time() - t0
        n_clf = clf["n"]

        t0 = time.time()
        sec = secrets_llm.evaluate_secret_detection(provider, df, neg_sample=NEG_SAMPLE, seed=0)
        t_sec = time.time() - t0
        n_sec = sec["eval_set_size"]

        results.append(
            {
                "modelo": model,
                "clasif_acierto": clf["llm_accuracy"],
                "clasif_s_por_prompt": round(t_clf / n_clf, 1) if n_clf else 0,
                "secretos_recall": sec["llm"]["recall"],
                "secretos_precision": sec["llm"]["precision"],
                "secretos_s_por_prompt": round(t_sec / n_sec, 1) if n_sec else 0,
                "caza_nl_password": any(
                    c["gt_secret_type"] == "password" for c in sec["caught_by_llm_only"]
                ),
            }
        )
        print(results[-1])

    print("\n=== RESUMEN ===")
    print(pd.DataFrame(results).to_string(index=False))
    # Para referencia: reglas (baseline sin IA) sobre la misma muestra.
    rule = classifier.evaluate_classifiers(
        OllamaProvider(MODELS[0]), df, per_category=PER_CATEGORY, seed=0
    )["rule_accuracy"]
    print(f"\nBaseline de reglas (sin IA) en clasificacion: {rule}")


if __name__ == "__main__":
    main()
