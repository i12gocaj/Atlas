"""Deteccion baseline de secretos y PII (sin IA).

Esta capa es deliberadamente "tonta": reglas regex mas entropia de Shannon. Su
papel es servir de BASELINE honesta para el contraste de la Semana 2: el LLM
debe superarla, sobre todo en el secreto en lenguaje natural (una contrasena
dictada en una frase) que ninguna regex pilla.
"""

from .baseline import detect_in_dataframe, evaluate_baseline  # noqa: F401
