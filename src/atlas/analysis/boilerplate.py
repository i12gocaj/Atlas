"""Deteccion de boilerplate repetido y sintesis de plantilla.

Idea: encontrar grupos de prompts que son la misma peticion reformulada (candidatos
a automatizar con una plantilla) y cuantificar el coste que consumen.

Decision de herramienta, alineada con "usar IA solo donde aporta":
- La DETECCION de casi-duplicados es similitud lexica TF-IDF (determinista, sin
  modelo). Es el tipo de problema que no necesita un LLM ni embeddings: los
  prompts repetidos comparten vocabulario de dominio. Probamos embeddings
  (nomic-embed-text) y en este contenido corto comprimian las similitudes sin
  separar bien, asi que TF-IDF es mas robusto y mas barato.
- La SINTESIS (nombrar el patron, escribir la plantilla canonica, decidir si es
  automatizable) si la hace el LLM generativo: eso es lo que solo el puede hacer.

La deteccion NO usa la etiqueta gt_is_boilerplate. La usamos solo despues para
validar honestamente (precision y recall).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..llm.base import LLMError, LLMProvider

# Stopwords minimas en espanol para limpiar el texto antes de vectorizar.
_STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "los", "las", "un", "una", "para", "con",
    "por", "que", "se", "del", "al", "lo", "como", "mas", "este", "esta", "su",
    "sus", "me", "mi", "te", "le", "es", "son", "the", "of", "to", "and",
}

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


@dataclass
class BoilerplateCluster:
    """Un grupo de prompts casi duplicados detectado en un equipo."""

    team: str
    size: int
    share_pct: float
    cluster_cost_eur: float
    estimated_savings_eur: float
    member_index: list[int] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    llm_summary: dict | None = None


def _tokenize(text: str) -> list[str]:
    """Normaliza (minusculas, sin acentos) y tokeniza, quitando stopwords."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return [t for t in _TOKEN_RE.findall(text) if len(t) > 2 and t not in _STOPWORDS]


def _tfidf_matrix(corpus: list[list[str]]) -> np.ndarray:
    """Matriz TF-IDF normalizada (n, vocab) a partir de textos tokenizados."""
    vocab: dict[str, int] = {}
    for tokens in corpus:
        for tok in tokens:
            vocab.setdefault(tok, len(vocab))
    n, v = len(corpus), len(vocab)
    if v == 0:
        return np.zeros((n, 0), dtype=np.float32)
    tf = np.zeros((n, v), dtype=np.float32)
    for i, tokens in enumerate(corpus):
        for tok in tokens:
            tf[i, vocab[tok]] += 1.0
    doc_freq = (tf > 0).sum(axis=0)
    idf = np.log((1 + n) / (1 + doc_freq)) + 1.0
    tfidf = tf * idf
    norms = np.linalg.norm(tfidf, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return tfidf / norms


def cluster_near_duplicates(
    texts: list[str], threshold: float = 0.5, min_size: int = 5
) -> list[list[int]]:
    """Agrupa textos casi duplicados por similitud coseno TF-IDF (greedy).

    Devuelve la lista de clusters (cada uno, lista de indices) con tamano minimo.
    """
    if not texts:
        return []
    matrix = _tfidf_matrix([_tokenize(t) for t in texts])
    sim = matrix @ matrix.T
    n = len(texts)
    assigned = np.zeros(n, dtype=bool)
    clusters: list[list[int]] = []
    for i in range(n):
        if assigned[i]:
            continue
        candidates = np.where((~assigned) & (sim[i] >= threshold))[0]
        if len(candidates) >= min_size:
            assigned[candidates] = True
            clusters.append(candidates.tolist())
        else:
            assigned[i] = True
    clusters.sort(key=len, reverse=True)
    return clusters


_SYSTEM = (
    "Eres un analista que detecta trabajo repetitivo en el uso de IA. Te paso "
    "varios prompts que un detector ha agrupado como la misma peticion reformulada. "
    "Resume el patron y propon como automatizarlo. Responde SOLO JSON, en espanol, "
    "sin guiones largos."
)


def summarize_cluster(provider: LLMProvider, examples: list[str]) -> dict:
    """Pide al LLM nombrar el patron y sintetizar una plantilla reutilizable."""
    joined = "\n".join(f"- {e}" for e in examples[:8])
    prompt = (
        f"Prompts agrupados como el mismo patron repetido:\n{joined}\n\n"
        "Devuelve JSON con esta forma exacta: "
        '{"nombre_patron": "...", '
        '"plantilla_sugerida": "<una plantilla o snippet que cubra todos los casos>", '
        '"automatizable": true|false, '
        '"recomendacion": "<una frase accionable>"}'
    )
    return provider.generate_json(prompt, system=_SYSTEM)


# Longitud minima de prompt para entrar al clustering. Filtra el autocompletado
# trivial ("completa la linea", "siguiente"), que es muy repetitivo pero NO es
# boilerplate automatizable: sin este filtro, el pico de coste de Pagos generaba
# cientos de falsos positivos.
MIN_PROMPT_CHARS = 25


def analyze_team(
    df: pd.DataFrame,
    team: str,
    provider: LLMProvider | None = None,
    threshold: float = 0.55,
    min_size: int = 15,
    min_share: float = 0.045,
    min_prompt_chars: int = MIN_PROMPT_CHARS,
) -> dict:
    """Detecta boilerplate en un equipo, lo cuantifica y (si hay LLM) lo sintetiza.

    Solo mira PRIMEROS INTENTOS sustantivos (is_retry False y prompt no trivial):
    el boilerplate es la peticion inicial repetida y con cuerpo, no los follow-ups
    de reintento ("sigue sin funcionar") ni el autocompletado trivial ("siguiente").
    El tamano minimo de cluster filtra el uso normal, que con un corpus variado no
    se concentra tanto como el boilerplate real.

    Incluye validacion honesta contra gt_is_boilerplate: la deteccion no la usa,
    solo la medimos despues. La funcion evaluate_detection_all_teams comprueba que
    la precision se sostiene en TODOS los equipos, no solo en el que tiene boilerplate.
    """
    substantive = df["prompt_text"].str.len() >= min_prompt_chars
    team_df = df[(df["team"] == team) & (~df["is_retry"]) & substantive].reset_index(drop=True)
    texts = team_df["prompt_text"].tolist()

    # Tamano minimo de cluster RELATIVO al volumen del equipo (con suelo absoluto).
    # Boilerplate es un patron que concentra una parte notable del uso del equipo,
    # no cualquier grupo que el volumen alto haga emerger. Sin esto, un equipo con
    # mucho volumen (Pagos en el pico) genera falsos positivos de uso normal.
    effective_min = max(min_size, round(min_share * len(team_df)))
    clusters = cluster_near_duplicates(texts, threshold=threshold, min_size=effective_min)

    team_events = len(team_df)
    detected_idx: set[int] = set()
    result_clusters: list[BoilerplateCluster] = []
    for members in clusters:
        detected_idx.update(members)
        sub = team_df.iloc[members]
        cost = float(sub["cost_eur"].sum())
        cluster = BoilerplateCluster(
            team=team,
            size=len(members),
            share_pct=round(len(members) / team_events * 100, 1) if team_events else 0.0,
            cluster_cost_eur=round(cost, 2),
            # Estimacion conservadora: automatizar elimina el 80% de esas
            # interacciones repetidas.
            estimated_savings_eur=round(cost * 0.8, 2),
            member_index=members,
            examples=sub["prompt_text"].head(5).tolist(),
        )
        result_clusters.append(cluster)

    # Validacion honesta contra ground truth.
    gt = team_df["gt_is_boilerplate"].astype(bool).to_numpy()
    pred = np.zeros(team_events, dtype=bool)
    if detected_idx:
        pred[list(detected_idx)] = True
    tp = int((gt & pred).sum())
    fp = int((~gt & pred).sum())
    fn = int((gt & ~pred).sum())
    precision = round(tp / (tp + fp), 3) if (tp + fp) else 0.0
    recall = round(tp / (tp + fn), 3) if (tp + fn) else 0.0

    # Sintesis con LLM del cluster mas grande (si hay proveedor). Si el modelo
    # falla, el analisis sigue siendo valido sin la sintesis.
    if provider and result_clusters:
        try:
            result_clusters[0].llm_summary = summarize_cluster(provider, result_clusters[0].examples)
        except LLMError:
            result_clusters[0].llm_summary = None

    return {
        "team": team,
        "team_events": team_events,
        "clusters_found": len(result_clusters),
        "detected_events": len(detected_idx),
        "detected_pct": round(len(detected_idx) / team_events * 100, 1) if team_events else 0.0,
        "validation_vs_gt": {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn},
        "clusters": [
            {
                "size": c.size,
                "share_pct": c.share_pct,
                "cluster_cost_eur": c.cluster_cost_eur,
                "estimated_savings_eur": c.estimated_savings_eur,
                "examples": c.examples,
                "llm_summary": c.llm_summary,
            }
            for c in result_clusters
        ],
    }


def evaluate_detection_all_teams(df: pd.DataFrame) -> list[dict]:
    """Valida la deteccion (sin LLM) en TODOS los equipos, para no hacer cherry-picking.

    Un detector honesto debe acertar donde HAY boilerplate (recall alto) y no
    inventarlo donde NO lo hay (pocos o cero detectados). Devuelve una fila por
    equipo con los detectados y la precision/recall vs ground truth.
    """
    rows = []
    for team in sorted(df["team"].unique()):
        analysis = analyze_team(df, team, provider=None)
        v = analysis["validation_vs_gt"]
        rows.append(
            {
                "team": team,
                "detected_events": analysis["detected_events"],
                "detected_pct": analysis["detected_pct"],
                "precision": v["precision"],
                "recall": v["recall"],
                "false_positives": v["fp"],
            }
        )
    return rows
