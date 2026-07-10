"""Capa LLM de Atlas, 100% local.

Proveedores detras de una interfaz comun (LLMProvider):
- OllamaProvider: modelo local, privado. El unico de produccion.
- StubProvider: canned, para tests y demo de respaldo.

No hay proveedores en la nube ni API keys: Atlas analiza prompts que pueden
contener secretos, asi que no deben salir de la maquina. La factory
`get_provider` devuelve el proveedor local.
"""

from .base import LLMError, LLMProvider, extract_json  # noqa: F401
from .factory import describe_provider, get_provider  # noqa: F401
from .stub import StubProvider  # noqa: F401
