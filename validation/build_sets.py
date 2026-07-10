"""Construye los sets de validacion GOLD, etiquetados a mano, bilingues (ES/EN).

Estos sets son independientes del dataset sintetico y sirven para medir con rigor,
no por intuicion, dos preguntas que la investigacion de herramientas dejo abiertas:

1. secrets_nl: deteccion de secretos y PII en LENGUAJE NATURAL. Mezcla:
   - positivos de baja entropia que solo la semantica revela (contrasenas dictadas
     en prosa), que regex y escaneres tipo Gitleaks NO cazan.
   - positivos estructurados y PII (que las herramientas SI cazan), para comparar.
   - negativos, incluidos los dificiles ("la clave primaria de la tabla", que
     menciona "clave" sin filtrar nada): miden falsos positivos.

2. intent: clasificacion de la categoria de tarea, 6 por categoria, mitad ES mitad
   EN, con etiquetas claras y defendibles.

Ejecutar: python validation/build_sets.py  (reescribe los .jsonl de esta carpeta).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent

# ---------------------------------------------------------------------------
# Set de secretos / PII en lenguaje natural
# Campos: id, lang, text, contains_secret, secret_type, hard_negative
# secret_type: password | api_key | connection_string | pii | null
# ---------------------------------------------------------------------------
SECRETS: list[dict] = [
    # --- Positivos: contrasena/credencial en prosa, baja entropia (solo LLM) ---
    {"lang": "es", "text": "la clave admin es verano2024 y el usuario es deploy_bot", "secret_type": "password"},
    {"lang": "es", "text": "para el deploy usa usuario root y contrasena root1234", "secret_type": "password"},
    {"lang": "es", "text": "el pin de acceso al panel de admin es 7788, pruebalo", "secret_type": "password"},
    {"lang": "es", "text": "credenciales de la demo: usuario demo, clave demo2024", "secret_type": "password"},
    {"lang": "es", "text": "pon como contrasena temporal hola123 hasta que rotemos", "secret_type": "password"},
    {"lang": "es", "text": "la wifi de la oficina es CafeConLeche2025, conectate", "secret_type": "password"},
    {"lang": "es", "text": "entra con admin y la clave es Admin2024 sin mas", "secret_type": "password"},
    {"lang": "es", "text": "te paso la cuenta de soporte: usuario soporte, password soporte_2024", "secret_type": "password"},
    {"lang": "es", "text": "la contrasena del correo de marketing es Marketing#2024", "secret_type": "password"},
    {"lang": "es", "text": "el usuario es ana y su clave personal es ana1990", "secret_type": "password"},
    {"lang": "en", "text": "the admin password is summer2024, log in and check", "secret_type": "password"},
    {"lang": "en", "text": "use root as user and root1234 as the password", "secret_type": "password"},
    {"lang": "en", "text": "the staging db password is just changeme", "secret_type": "password"},
    {"lang": "en", "text": "set a temp password like hello123 for the deploy", "secret_type": "password"},
    {"lang": "en", "text": "the office wifi password is CoffeeLover2025", "secret_type": "password"},
    {"lang": "en", "text": "login with admin and the password is Admin2024", "secret_type": "password"},
    {"lang": "en", "text": "the support account password is support_2024", "secret_type": "password"},
    {"lang": "en", "text": "the prod api secret is literally banana-phone-42", "secret_type": "password"},
    # --- Positivos estructurados / PII (las herramientas tambien los cazan) ---
    {"lang": "es", "text": "el IBAN de la cuenta es ES9121000418450200051332", "secret_type": "pii"},
    {"lang": "es", "text": "la tarjeta de pruebas es 4111111111111111", "secret_type": "pii"},
    {"lang": "es", "text": "el DNI del cliente de prueba es 12345678Z", "secret_type": "pii"},
    {"lang": "en", "text": "my social security number is 078-05-1120", "secret_type": "pii"},
    {
        "lang": "en",
        "text": "send the demo token atlas-demo-g7Kq2Zp9rX4vB1nM8cT5wY",
        "secret_type": "api_key",
    },
    {"lang": "en", "text": "connect with postgres://user:Pr0dPass2026@db.internal:5432/app", "secret_type": "connection_string"},
    # --- Negativos dificiles: mencionan palabras de secreto sin filtrar nada ---
    {"lang": "es", "text": "la clave primaria de la tabla ventas es id_venta", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "la clave foranea apunta a la tabla clientes", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "como reseteo mi contrasena si la olvide", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "necesito una funcion que valide la contrasena del usuario", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "documenta el campo password de la tabla usuarios", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "explicame como funciona el hashing de contrasenas con bcrypt", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "el token de sesion expira a los 30 minutos, configuralo", "secret_type": None, "hard_negative": True},
    {"lang": "es", "text": "quiero rotar las credenciales cada 90 dias, como lo hago", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "how do I reset my password if I forgot it", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "write a function that validates the user password", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "where should I store the API key securely", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "please dont hardcode the password in the config file", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "the primary key of the orders table is order_id", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "mock the auth token in the test, dont use a real one", "secret_type": None, "hard_negative": True},
    # --- Negativos normales: prompts de desarrollo sin secretos ---
    {"lang": "es", "text": "implementa una funcion que agregue ventas por mes", "secret_type": None},
    {"lang": "es", "text": "documenta el proceso de carga de la tabla clientes", "secret_type": None},
    {"lang": "es", "text": "genera tests unitarios para la transformacion de pagos", "secret_type": None},
    {"lang": "es", "text": "analiza la evolucion del importe el ultimo trimestre", "secret_type": None},
    {"lang": "en", "text": "the deploy fails with a duplicate key error, why", "secret_type": None},
    {"lang": "en", "text": "refactor this module to separate data access from logic", "secret_type": None},
    {"lang": "en", "text": "add a password strength meter to the signup form", "secret_type": None, "hard_negative": True},
    {"lang": "en", "text": "what is the best way to rotate secrets in production", "secret_type": None, "hard_negative": True},
]

# ---------------------------------------------------------------------------
# Set de intencion (clasificacion de categoria de tarea)
# Campos: id, lang, text, category
# ---------------------------------------------------------------------------
INTENT: list[dict] = [
    # codigo
    {"lang": "es", "text": "implementa una funcion en python que agregue ventas por mes", "category": "codigo"},
    {"lang": "es", "text": "crea un endpoint REST que devuelva los pedidos por cliente", "category": "codigo"},
    {"lang": "es", "text": "anade paginacion con cursor al listado de facturas", "category": "codigo"},
    {"lang": "en", "text": "write a function to parse the CSV and return typed objects", "category": "codigo"},
    {"lang": "en", "text": "refactor this class to inject the database connection", "category": "codigo"},
    {"lang": "en", "text": "implement retry with backoff for the http client", "category": "codigo"},
    # documentacion
    {"lang": "es", "text": "documenta el proceso de carga de la tabla clientes con sus reglas", "category": "documentacion"},
    {"lang": "es", "text": "escribe el diccionario de datos de la tabla pagos", "category": "documentacion"},
    {"lang": "es", "text": "redacta la nota de version del cambio en el esquema", "category": "documentacion"},
    {"lang": "en", "text": "write the README with setup and deploy instructions", "category": "documentacion"},
    {"lang": "en", "text": "document the validation rules applied to invoices", "category": "documentacion"},
    {"lang": "en", "text": "create a functional guide of the reconciliation service", "category": "documentacion"},
    # pruebas
    {"lang": "es", "text": "genera tests unitarios para la transformacion de pagos con casos nulos", "category": "pruebas"},
    {"lang": "es", "text": "disena casos UAT para validar el calculo de comisiones", "category": "pruebas"},
    {"lang": "es", "text": "crea fixtures realistas de la tabla ventas para los tests", "category": "pruebas"},
    {"lang": "en", "text": "write integration tests for the orders endpoint", "category": "pruebas"},
    {"lang": "en", "text": "add a regression test for the negative amount bug", "category": "pruebas"},
    {"lang": "en", "text": "property based tests for the aggregation function", "category": "pruebas"},
    # requisitos
    {"lang": "es", "text": "a partir de esta peticion de negocio extrae los requisitos tecnicos", "category": "requisitos"},
    {"lang": "es", "text": "convierte esta historia de usuario en criterios de aceptacion", "category": "requisitos"},
    {"lang": "es", "text": "especifica las reglas de calidad de dato para la tabla pagos", "category": "requisitos"},
    {"lang": "en", "text": "define the minimal data model to support invoices", "category": "requisitos"},
    {"lang": "en", "text": "list the questions to ask business before building this", "category": "requisitos"},
    {"lang": "en", "text": "turn this business goal into a phased technical scope", "category": "requisitos"},
    # debug
    {"lang": "es", "text": "el proceso falla al cruzar ventas con cuentas, error de clave duplicada", "category": "debug"},
    {"lang": "es", "text": "tengo una fuga de memoria en el job de facturas, donde esta", "category": "debug"},
    {"lang": "es", "text": "despues del despliegue el campo importe llega en nulo, ayudame", "category": "debug"},
    {"lang": "en", "text": "the deploy fails authenticating, why does it reject the login", "category": "debug"},
    {"lang": "en", "text": "the cost calculation gives different results each run, why", "category": "debug"},
    {"lang": "en", "text": "the service is slow only in production, where do I start", "category": "debug"},
    # analisis
    {"lang": "es", "text": "analiza la evolucion del importe en ventas el ultimo trimestre", "category": "analisis"},
    {"lang": "es", "text": "compara dos enfoques para calcular las comisiones y recomienda uno", "category": "analisis"},
    {"lang": "es", "text": "cuantifica cuanto del coste viene de la tabla ventas", "category": "analisis"},
    {"lang": "en", "text": "estimate the impact on latency of moving to batch processing", "category": "analisis"},
    {"lang": "en", "text": "detect anomalies in the payments table over the last month", "category": "analisis"},
    {"lang": "en", "text": "why did the error rate get worse last week, cross deploys and volume", "category": "analisis"},
]


def _write(name: str, rows: list[dict]) -> None:
    path = HERE / name
    with path.open("w", encoding="utf-8") as fh:
        for i, row in enumerate(rows):
            record = {"id": f"{name.split('.')[0]}_{i:03d}", **row}
            if name.startswith("secrets"):
                record.setdefault("hard_negative", False)
                record["contains_secret"] = record["secret_type"] is not None
            fh.write(json.dumps(record, ensure_ascii=False))
            fh.write("\n")
    print(f"{path}: {len(rows)} casos")


if __name__ == "__main__":
    _write("secrets_nl.jsonl", SECRETS)
    _write("intent.jsonl", INTENT)
