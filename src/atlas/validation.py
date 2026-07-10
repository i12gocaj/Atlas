"""Arnes de evaluacion sobre el set de validacion GOLD (etiquetado a mano).

Mide, con rigor y de forma repetible, dos preguntas que la investigacion de
herramientas dejo abiertas:

- Secretos en lenguaje natural: el LLM frente a la baseline determinista
  (regex + entropia + detect-secrets), con foco en los positivos de baja entropia
  (contrasenas dictadas en prosa) y en los negativos dificiles (falsos positivos).
- Clasificacion de intencion: el LLM frente a las reglas por palabras clave.

Carga los .jsonl de la carpeta `validation/`. No depende del dataset sintetico.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .analysis import classifier, secrets_llm
from .detection import baseline, pii
from .llm.base import LLMProvider

DEFAULT_VALIDATION_DIR = Path("validation")


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson para una proporcion k/n (95% por defecto).

    Honesto con muestras pequenas: 'recall 1.0 sobre 18 casos' no es 1.0 de
    verdad. Wilson da el rango plausible (formula cerrada, sin dependencias).
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, center - half), 3), round(min(1.0, center + half), 3))


def load_jsonl(path: str | Path) -> list[dict]:
    """Carga un fichero JSONL en una lista de diccionarios."""
    rows: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _binary_metrics(truth: list[bool], pred: list[bool]) -> dict:
    tp = sum(1 for t, p in zip(truth, pred) if t and p)
    fp = sum(1 for t, p in zip(truth, pred) if not t and p)
    fn = sum(1 for t, p in zip(truth, pred) if t and not p)
    tn = sum(1 for t, p in zip(truth, pred) if not t and not p)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
    }


def evaluate_secrets(provider: LLMProvider, path: str | Path | None = None) -> dict:
    """Compara baseline (herramienta) vs LLM en deteccion de secretos en prosa."""
    rows = load_jsonl(path or DEFAULT_VALIDATION_DIR / "secrets_nl.jsonl")
    truth = [bool(r["contains_secret"]) for r in rows]

    base_pred = [len(baseline.detect_secrets_in_text(r["text"])) > 0 for r in rows]
    llm_pred = [secrets_llm.llm_detect_secret(provider, r["text"])["contains_secret"] for r in rows]

    # Foco 1: recall sobre los positivos en lenguaje natural (baja entropia), que
    # son el territorio exclusivo del LLM.
    nl_idx = [i for i, r in enumerate(rows) if r.get("secret_type") == "password"]
    nl_base = sum(1 for i in nl_idx if base_pred[i])
    nl_llm = sum(1 for i in nl_idx if llm_pred[i])

    # Foco 2: falsos positivos sobre negativos dificiles (mencionan "clave"/"password"
    # sin filtrar nada).
    hard_idx = [i for i, r in enumerate(rows) if r.get("hard_negative") and not r["contains_secret"]]
    hard_base_fp = sum(1 for i in hard_idx if base_pred[i])
    hard_llm_fp = sum(1 for i in hard_idx if llm_pred[i])

    return {
        "n": len(rows),
        "positivos": sum(truth),
        "baseline": _binary_metrics(truth, base_pred),
        "llm": _binary_metrics(truth, llm_pred),
        "lenguaje_natural": {
            "positivos": len(nl_idx),
            "recall_baseline": round(nl_base / len(nl_idx), 3) if nl_idx else 0.0,
            "recall_llm": round(nl_llm / len(nl_idx), 3) if nl_idx else 0.0,
        },
        "negativos_dificiles": {
            "n": len(hard_idx),
            "falsos_positivos_baseline": hard_base_fp,
            "falsos_positivos_llm": hard_llm_fp,
        },
    }


def evaluate_pii(path: str | Path | None = None) -> dict:
    """Mide el detector determinista de PII sobre el set gold (solo herramienta).

    La PII estructurada (IBAN, DNI/NIE, tarjeta) es territorio de herramienta:
    regex mas digito de control. El valor esta en la precision: el checksum
    descarta los senuelos (un IBAN o una tarjeta con digito de control invalido),
    algo que un LLM no puede calcular de forma fiable. No comparamos con el LLM
    aqui porque seria forzarlo donde la herramienta ya es el instrumento correcto.
    """
    rows = load_jsonl(path or DEFAULT_VALIDATION_DIR / "pii.jsonl")
    truth = [bool(r["contains_pii"]) for r in rows]
    detections = [pii.detect_pii(r["text"]) for r in rows]
    pred = [len(d) > 0 for d in detections]

    # Senuelos: cadenas con pinta de PII pero con checksum invalido. La herramienta
    # debe descartarlos todos (cero falsos positivos).
    hard_idx = [i for i, r in enumerate(rows) if r.get("hard_negative")]
    hard_fp = sum(1 for i in hard_idx if pred[i])

    # Aciertos de TIPO, no solo de contiene/no-contiene: para cada positivo, los
    # tipos detectados deben ser EXACTAMENTE el tipo esperado (ni de menos ni de
    # mas, p.ej. un fragmento de IBAN reetiquetado como tarjeta seria un error).
    type_errors = 0
    for r, det in zip(rows, detections):
        if not r["contains_pii"]:
            continue
        detected = {d["type"] for d in det}
        if detected != {r["pii_type"]}:
            type_errors += 1

    return {
        "n": len(rows),
        "positivos": sum(truth),
        "herramienta": _binary_metrics(truth, pred),
        "errores_de_tipo": type_errors,
        "senuelos": {
            "n": len(hard_idx),
            "falsos_positivos": hard_fp,
        },
    }


def evaluate_intent(provider: LLMProvider, path: str | Path | None = None) -> dict:
    """Compara reglas vs LLM en clasificacion de intencion, con desglose por idioma."""
    rows = load_jsonl(path or DEFAULT_VALIDATION_DIR / "intent.jsonl")
    rule_hits = 0
    llm_hits = 0
    by_lang: dict[str, dict[str, int]] = {}
    details = []
    for r in rows:
        truth = r["category"]
        rule_pred = classifier.rule_classify(r["text"])
        llm_pred = classifier.llm_classify(provider, r["text"])
        rule_ok = rule_pred == truth
        llm_ok = llm_pred == truth
        rule_hits += int(rule_ok)
        llm_hits += int(llm_ok)
        lang = r.get("lang", "?")
        bucket = by_lang.setdefault(lang, {"n": 0, "rule": 0, "llm": 0})
        bucket["n"] += 1
        bucket["rule"] += int(rule_ok)
        bucket["llm"] += int(llm_ok)
        details.append({"text": r["text"][:80], "truth": truth, "rule": rule_pred, "llm": llm_pred})

    n = len(rows)
    return {
        "n": n,
        "rule_accuracy": round(rule_hits / n, 3) if n else 0.0,
        "llm_accuracy": round(llm_hits / n, 3) if n else 0.0,
        "por_idioma": {
            lang: {
                "n": b["n"],
                "rule_accuracy": round(b["rule"] / b["n"], 3),
                "llm_accuracy": round(b["llm"] / b["n"], 3),
            }
            for lang, b in by_lang.items()
        },
        "details": details,
    }
