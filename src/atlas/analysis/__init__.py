"""Capa de analisis con IA de Atlas (el cerebro, Semana 2).

Aqui vive lo que SOLO la IA puede hacer, sobre la base de cifras deterministas
de la capa de señales:

- classifier: clasifica la categoria de tarea leyendo el prompt (contraste
  reglas contra LLM, validado contra ground truth).
- secrets_llm: detector de secretos por LLM que caza el secreto en lenguaje
  natural que la baseline de reglas no pilla.
- brief: el agente analista que redacta el brief ejecutivo de gobernanza a
  partir de las señales, sin inventar cifras.

Todo depende de la interfaz LLMProvider (atlas.llm), no de un modelo concreto.
"""
