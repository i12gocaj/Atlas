"""Detector de secretos estructurados (sin IA): herramienta especializada.

Para detectar secretos de patron fijo (claves, tokens, cadenas de conexion) un
LLM no aporta valor: es una tarea determinista y verificable donde gana el
tooling. Por eso aqui combinamos, en UNION, tres motores deterministas:

1. detect-secrets (Yelp), SOLO sus detectores estructurados: aporta ~20 tipos
   bien definidos (Slack, Stripe, JWT, claves privadas, Azure, GitLab, etc).
   Sus plugins de ENTROPIA se desactivan a proposito: son demasiado ruidosos
   sobre prosa (marcan prompts normales como secreto).
2. Nuestros patrones regex: cubren tipos que detect-secrets no caza en este
   dataset (el token sintetico sk-live-..., AKIA con EXAMPLE, Google AIza).
3. Entropia de Shannon propia, conservadora (tokens de longitud >= 20).

Esta union es deliberada: la investigacion de herramientas mostro que
detect-secrets NO debe reemplazar a la regex (regresionaria en casos que hoy se
cazan), sino complementarla. Lo unico que NINGUNO de estos motores cubre es el
secreto en LENGUAJE NATURAL ("la clave admin es verano2024"): ese hueco es del
LLM, y es el corazon del contraste reglas contra IA del pitch.

Si detect-secrets no esta instalado, el detector degrada con elegancia a regex
mas entropia (la libreria es opcional).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import pandas as pd

# detect-secrets es opcional: si no esta, degradamos a regex mas entropia.
try:
    from detect_secrets.core import scan as _ds_scan
    from detect_secrets.settings import get_settings as _ds_get_settings

    _HAS_DETECT_SECRETS = True
except ImportError:  # pragma: no cover
    _HAS_DETECT_SECRETS = False

# Solo detectores ESTRUCTURADOS de detect-secrets. Excluimos a proposito los de
# entropia (Base64/Hex HighEntropyString) porque marcan prosa normal como secreto.
_DS_STRUCTURED_PLUGINS = [
    "AWSKeyDetector", "GitHubTokenDetector", "BasicAuthDetector", "PrivateKeyDetector",
    "SlackDetector", "StripeDetector", "JwtTokenDetector", "AzureStorageKeyDetector",
    "GitLabTokenDetector", "NpmDetector", "SendGridDetector", "TwilioKeyDetector",
    "SquareOAuthDetector", "MailchimpDetector", "ArtifactoryDetector",
    "DiscordBotTokenDetector", "IbmCloudIamDetector", "SoftlayerDetector",
]
_ds_configured = False

# Patrones de secretos estructurados. Cada uno con un nombre de tipo.
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("connection_string", re.compile(r"[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s:/@]+@[^\s/]+", re.IGNORECASE)),
    ("api_key", re.compile(r"\bAKIA[0-9A-Z]{8,}\b")),
    ("api_key", re.compile(r"\bghp_[0-9A-Za-z]{20,}\b")),
    ("api_key", re.compile(r"\bsk-[0-9A-Za-z\-]{16,}\b")),
    ("api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b")),
]

# Parametros de la deteccion por entropia (para tokens aparentemente aleatorios).
ENTROPY_MIN_LENGTH = 20
ENTROPY_THRESHOLD = 3.5  # bits por caracter
_TOKEN_RE = re.compile(r"[A-Za-z0-9\-_]{%d,}" % ENTROPY_MIN_LENGTH)


def _looks_like_words(token: str) -> bool:
    """True si el token son palabras humanas unidas por guiones o subrayados.

    'infraestructura-y-plataforma' o 'ATLAS_DASHBOARD_OUTPUT_DIR' superan el
    umbral de entropia sin ser secretos. Un secreto real (base62, hex, token
    aleatorio) casi siempre mezcla letras y digitos dentro de un mismo
    fragmento; si cada fragmento es solo letras o solo digitos, es prosa o una
    constante, no un secreto.
    """
    fragments = [f for f in re.split(r"[-_]", token) if f]
    return all(f.isalpha() or f.isdigit() for f in fragments)


@dataclass
class SecretFinding:
    """Un hallazgo de secreto en un texto."""

    secret_type: str
    method: str  # "regex", "entropy" o "detect-secrets"
    match: str


def _ensure_ds_configured() -> None:
    """Configura los plugins estructurados de detect-secrets una sola vez."""
    global _ds_configured
    if _HAS_DETECT_SECRETS and not _ds_configured:
        _ds_get_settings().configure_plugins([{"name": n} for n in _DS_STRUCTURED_PLUGINS])
        _ds_configured = True


def _detect_secrets_findings(text: str) -> list[SecretFinding]:
    """Hallazgos de la libreria detect-secrets (solo detectores estructurados)."""
    if not _HAS_DETECT_SECRETS:
        return []
    _ensure_ds_configured()
    out: list[SecretFinding] = []
    for secret in _ds_scan.scan_line(text):
        out.append(SecretFinding(str(secret.type), "detect-secrets", (secret.secret_value or "")[:40]))
    return out


def shannon_entropy(text: str) -> float:
    """Entropia de Shannon (bits por caracter) de una cadena."""
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def detect_secrets_in_text(text: str) -> list[SecretFinding]:
    """Devuelve los hallazgos de secreto en un texto (union de los tres motores)."""
    findings: list[SecretFinding] = []
    if not isinstance(text, str) or not text:
        return findings

    # 1) Nuestros patrones regex.
    for secret_type, pattern in SECRET_PATTERNS:
        for match in pattern.findall(text):
            value = match if isinstance(match, str) else match[0]
            findings.append(SecretFinding(secret_type, "regex", value))

    # 2) Entropia de Shannon propia (tokens largos no pillados ya por un patron).
    already = {f.match for f in findings}
    for token in _TOKEN_RE.findall(text):
        if token in already or _looks_like_words(token):
            continue
        if shannon_entropy(token) >= ENTROPY_THRESHOLD:
            findings.append(SecretFinding("high_entropy", "entropy", token))

    # 3) detect-secrets, solo detectores estructurados (cobertura adicional).
    findings.extend(_detect_secrets_findings(text))

    return findings


def detect_in_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Anade columnas de prediccion de secreto al DataFrame de eventos.

    Columnas nuevas:
    - pred_contains_secret (bool)
    - pred_secret_types (str, tipos separados por coma)
    - pred_method (str, metodos que dispararon)
    """
    result = df.copy()
    preds = result["prompt_text"].map(detect_secrets_in_text)
    result["pred_contains_secret"] = preds.map(lambda fs: len(fs) > 0)
    result["pred_secret_types"] = preds.map(
        lambda fs: ",".join(sorted({f.secret_type for f in fs}))
    )
    result["pred_method"] = preds.map(lambda fs: ",".join(sorted({f.method for f in fs})))
    return result


def evaluate_baseline(df: pd.DataFrame) -> dict:
    """Evalua la baseline contra el ground truth (gt_contains_secret).

    Devuelve precision, recall, F1 y el detalle de TP/FP/FN/TN, mas la lista de
    los secretos que se ESCAPARON (lo que el LLM tendra que cazar en la Semana 2).
    """
    scored = detect_in_dataframe(df)
    truth = scored["gt_contains_secret"].astype(bool)
    pred = scored["pred_contains_secret"].astype(bool)

    tp = int((truth & pred).sum())
    fp = int((~truth & pred).sum())
    fn = int((truth & ~pred).sum())
    tn = int((~truth & ~pred).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    missed = scored[truth & ~pred][["event_id", "team", "user_id", "gt_secret_type", "prompt_text"]]

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "missed_secrets": missed.to_dict(orient="records"),
    }
