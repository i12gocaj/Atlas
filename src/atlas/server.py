"""Servidor estatico ligero para la demo: sirve el dashboard, nada mas.

Sin API ni dependencia del modelo: el dashboard es estatico y se sirve tal cual.
La deteccion en vivo (secretos, PII) la hace el presentador desde la terminal;
por seguridad, la entrada sensible puede llegar por stdin y no se vuelve a mostrar.
"""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silencio en consola
        pass


def serve(dashboard_dir: str = "dashboard", port: int = 8777) -> None:
    """Sirve el dashboard estatico en localhost."""
    handler = partial(_QuietHandler, directory=dashboard_dir)
    # La demo es estrictamente local: una direccion vacia escucharia en todas
    # las interfaces de red y expondria el dashboard sin necesidad.
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Atlas en http://127.0.0.1:{port}  (Ctrl+C para parar)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
        httpd.shutdown()
