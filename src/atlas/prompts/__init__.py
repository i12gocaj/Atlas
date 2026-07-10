"""Generacion del corpus de texto de los prompts y respuestas.

`templates.py` contiene el material crudo (plantillas curadas). `corpus.py` lo
combina de forma determinista para producir prompts realistas.

Nota de evolucion: en la Semana 1 el corpus es plantillado y reproducible, sin
dependencias externas. Esta aislado a proposito detras de `corpus.build_pools`
para poder sustituirlo, si interesa, por un corpus generado una sola vez con un
LLM y congelado, sin tocar el generador de eventos.
"""
