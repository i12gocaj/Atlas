"""Material crudo para construir los prompts y respuestas sinteticos.

Los prompts llevan placeholders entre llaves ({tabla}, {servicio}, ...) que
`corpus.py` rellena con vocabulario realista. Hay dos registros por categoria:

- SENIOR: prompts ricos, con contexto, rol, formato esperado y criterios.
- JUNIOR: prompts vagos, cortos, sin contexto, que disparan reintentos.

Esta separacion es la materia prima del valor de Atlas: el clasificador y el
analisis semantico de la Semana 2 deben distinguir un buen prompt de uno malo
leyendo el texto, algo que una regla por palabras clave no puede hacer.

Importante: ningun texto usa guiones largos. Solo comas, dos puntos o
parentesis, igual que en el resto del proyecto.
"""

from __future__ import annotations

# Vocabulario para rellenar placeholders. Cuanto mas variado, mas realistas y
# menos repetitivos son los prompts normales (clave para que el boilerplate
# repetido destaque de verdad frente al uso normal).
VOCAB: dict[str, list[str]] = {
    "tabla": [
        "ventas", "clientes", "movimientos", "cuentas", "productos", "pagos",
        "pedidos", "devoluciones", "facturas", "saldos", "comisiones", "tarifas",
    ],
    "servicio": [
        "pasarela de pagos", "ledger", "conciliacion", "reporting", "onboarding",
        "antifraude", "liquidacion", "notificaciones", "agregacion bancaria",
    ],
    "campo": [
        "importe", "fecha_valor", "id_cliente", "estado", "divisa", "saldo",
        "iban", "comision", "tipo_operacion", "canal", "pais", "segmento",
    ],
    "lenguaje": ["Python", "SQL", "PySpark", "TypeScript", "Scala", "Java"],
    "entidad": ["factura", "transaccion", "abono", "cargo", "asiento", "recibo", "mandato"],
    "metrica": ["latencia", "tasa de error", "throughput", "tiempo de proceso", "coste"],
    "periodo": ["el ultimo mes", "el trimestre", "la ultima semana", "el ano fiscal"],
}


# ---------------------------------------------------------------------------
# Prompts SENIOR por categoria (ricos y especificos)
# ---------------------------------------------------------------------------
SENIOR_PROMPTS: dict[str, list[str]] = {
    "codigo": [
        "Implementa en {lenguaje} una funcion que agregue {tabla} por {campo} y "
        "devuelva el total por mes. El dataframe ya esta cargado y tipado. "
        "Formato de salida: codigo con docstring y manejo de nulos.",
        "Necesito un endpoint que exponga {entidad} filtrando por {campo}. Usa el "
        "patron repositorio que ya tenemos, valida la entrada y devuelve errores "
        "4xx con mensaje claro. Incluye los tipos.",
        "Refactoriza este modulo de {servicio} para separar la logica de acceso a "
        "datos de la de negocio. Manten la interfaz publica y anade tipos.",
        "Escribe una funcion en {lenguaje} que normalice el {campo} de {tabla} a "
        "mayusculas y elimine espacios, vectorizada para no iterar fila a fila.",
        "Crea una clase repositorio para {entidad} con metodos de alta, baja y "
        "consulta por {campo}, inyectando la conexion para poder testear.",
        "Optimiza esta consulta {lenguaje} que agrega {tabla} por {campo}: tarda "
        "demasiado. Propon indices o reescritura y explica el porque.",
        "Genera un parser que lea {entidad} en CSV y devuelva objetos validados, "
        "rechazando filas con {campo} ausente o mal formado.",
        "Implementa la paginacion del listado de {entidad} en el {servicio}, con "
        "cursor estable por {campo} y limite configurable.",
    ],
    "documentacion": [
        "Documenta el proceso de carga de {tabla} siguiendo nuestra plantilla: "
        "origen, transformaciones, reglas de negocio y campos calculados. Publica "
        "en Markdown con tabla de campos (nombre, tipo, nulo, PK).",
        "Redacta la guia funcional del {servicio}: que hace, entradas, salidas y "
        "el flujo del dato de origen a consumo. Tono claro para alguien nuevo.",
        "Escribe el diccionario de datos de {tabla}: por cada {campo}, su tipo, si "
        "admite nulos y su significado de negocio.",
        "Genera el README del repositorio del {servicio} con arquitectura, como "
        "arrancar en local y como desplegar.",
        "Documenta las reglas de validacion que aplicamos a {entidad} antes de "
        "persistirla, con un ejemplo valido y uno invalido por regla.",
        "Prepara un runbook de operacion del {servicio}: alertas habituales, como "
        "diagnosticar y a quien escalar.",
        "Redacta la nota de version del cambio en {tabla}: que cambia, impacto en "
        "consumidores y pasos de migracion.",
    ],
    "pruebas": [
        "Genera pruebas unitarias para la transformacion de {tabla}: casos con "
        "nulos, duplicados y {campo} fuera de rango. Usa pytest y datos "
        "deterministas.",
        "Disena casos UAT para validar que el calculo de {campo} sobre {entidad} "
        "cuadra con el requisito. Incluye entrada y salida esperada.",
        "Escribe tests de integracion del {servicio} contra una base efimera, "
        "cubriendo el alta y la consulta de {entidad}.",
        "Crea property based tests para la funcion que agrega {tabla} por {campo}, "
        "comprobando invariantes con datos generados.",
        "Anade pruebas de regresion para el bug del {campo} negativo en {entidad} "
        "que aparecio el {periodo}.",
        "Genera fixtures realistas de {tabla} para los tests, con variedad de "
        "{campo} y casos limite.",
    ],
    "requisitos": [
        "A partir de esta peticion de negocio, extrae los requisitos tecnicos: que "
        "datos necesito de {tabla}, que transformaciones y que salida espera el "
        "usuario del {servicio}. Estructura en lista numerada.",
        "Convierte esta historia de usuario en criterios de aceptacion medibles "
        "para el {servicio}, separando funcionales y no funcionales.",
        "Define el modelo de datos minimo para soportar {entidad} en el "
        "{servicio}, con entidades, relaciones y claves.",
        "Lista las preguntas que hay que hacerle a negocio antes de construir el "
        "calculo de {campo} sobre {tabla}.",
        "Especifica las reglas de calidad de dato que debe cumplir {tabla} para "
        "que el {servicio} pueda fiarse de ella.",
        "Traduce este objetivo de negocio sobre {entidad} a un alcance tecnico "
        "por fases, con un MVP claro.",
    ],
    "debug": [
        "El proceso del {servicio} falla al cruzar {tabla} con cuentas: salta un "
        "error de clave duplicada. Aqui tienes el stacktrace. Razona la causa "
        "antes de proponer el fix.",
        "Tengo una fuga de memoria en el job que procesa {entidad}. Te paso el "
        "perfil de uso y el bucle principal. Donde esta el problema.",
        "El calculo de {campo} en {tabla} da resultados distintos entre dos "
        "ejecuciones con los mismos datos. Que puede causar el no determinismo.",
        "El {servicio} responde lento solo en produccion. Misma version que en "
        "test. Por donde empiezo a investigar.",
        "Un job de carga de {tabla} se queda colgado sin error. Como lo diagnostico "
        "sin parar el proceso.",
        "Despues del ultimo despliegue, {entidad} llega con el {campo} en nulo. "
        "Ayudame a localizar el cambio que lo rompio.",
    ],
    "analisis": [
        "Analiza la evolucion de {campo} en {tabla} {periodo} y dime que patron "
        "explica el cambio. Necesito la hipotesis y como verificarla con los datos.",
        "Compara dos enfoques para calcular {campo} sobre {entidad} y recomienda "
        "uno justificando coste y mantenibilidad.",
        "Estima el impacto en {metrica} de mover el {servicio} a procesamiento por "
        "lotes frente a streaming.",
        "Detecta anomalias en {tabla} {periodo}: que {campo} se sale de su rango "
        "habitual y con que severidad.",
        "Cuantifica cuanto del {metrica} del {servicio} viene de {tabla} frente al "
        "resto, para priorizar la optimizacion.",
        "Explica por que la {metrica} del {servicio} empeoro {periodo} cruzando "
        "despliegues y volumen de {entidad}.",
    ],
}


# ---------------------------------------------------------------------------
# Prompts JUNIOR por categoria (vagos y sin contexto)
# ---------------------------------------------------------------------------
JUNIOR_PROMPTS: dict[str, list[str]] = {
    "codigo": [
        "hazme una funcion para {tabla}",
        "como saco el total de {campo}",
        "codigo para esto en {lenguaje}",
        "monta el endpoint de {entidad}",
        "script rapido para {tabla}",
        "pasame esto a {lenguaje}",
    ],
    "documentacion": [
        "documenta esto",
        "escribe la doc de {tabla}",
        "que campos tiene {tabla}",
        "hazme el readme del {servicio}",
    ],
    "pruebas": [
        "ponme tests",
        "test para {tabla}",
        "cubre esto con pruebas",
        "un test del {campo}",
    ],
    "requisitos": [
        "que necesito para el {servicio}",
        "saca los requisitos de esto",
        "que datos hacen falta de {tabla}",
        "como lo planteo",
    ],
    "debug": [
        "no funciona",
        "da error arregla {tabla}",
        "por que peta esto",
        "el {campo} sale mal",
        "esto va lento",
    ],
    "analisis": [
        "analiza {tabla}",
        "que pasa con {campo}",
        "mira la {metrica} del {servicio}",
        "esto sube o baja {periodo}",
    ],
}


# ---------------------------------------------------------------------------
# Follow-ups de reintento (cadenas de iteraciones en una sesion)
# ---------------------------------------------------------------------------
RETRY_FOLLOWUPS: list[str] = [
    "sigue sin funcionar",
    "no es eso",
    "ahora da otro error",
    "eso ya lo probe",
    "mas concreto",
    "no me vale, hazlo otra vez",
    "el resultado no cuadra",
]


# ---------------------------------------------------------------------------
# Respuestas resumidas por categoria (lo que devolveria el asistente)
# ---------------------------------------------------------------------------
RESPONSE_SUMMARIES: dict[str, list[str]] = {
    "codigo": [
        "Funcion en {lenguaje} con docstring y manejo de nulos.",
        "Endpoint con validacion y tipos, siguiendo el patron repositorio.",
    ],
    "documentacion": [
        "Documento Markdown con tabla de campos y reglas de negocio.",
        "Guia funcional con flujo del dato de origen a consumo.",
    ],
    "pruebas": [
        "Suite pytest con casos de nulos, duplicados y rangos.",
        "Casos UAT con datos de entrada y salida esperada.",
    ],
    "requisitos": [
        "Lista numerada de requisitos tecnicos y fuentes de datos.",
        "Criterios de aceptacion funcionales y no funcionales.",
    ],
    "debug": [
        "Diagnostico de causa raiz y fix propuesto.",
        "Identificacion del cuello de botella y correccion.",
    ],
    "analisis": [
        "Hipotesis del patron y plan de verificacion con datos.",
        "Comparativa de enfoques con recomendacion justificada.",
    ],
}


# ---------------------------------------------------------------------------
# Escenario: autocompletado trivial (pico de coste en Pagos)
# ---------------------------------------------------------------------------
# Peticiones minimas que NO justifican un modelo caro. El valor del escenario
# es ese desajuste: tarea trivial resuelta con el modelo mas caro, muy a menudo.
TRIVIAL_PROMPTS: list[str] = [
    "completa la linea",
    "siguiente",
    "// completa",
    "termina el for",
    "autocompleta esto",
    "cierra el bloque",
    "el import que falta",
    "renombra la variable",
]

TRIVIAL_RESPONSE = "Sugerencia de autocompletado de una linea."


# ---------------------------------------------------------------------------
# Escenario: boilerplate repetido (Datos)
# ---------------------------------------------------------------------------
# Diez reformulaciones de LA MISMA peticion. A ojo de una query SQL son prompts
# distintos; solo el analisis semantico ve que son el mismo boilerplate.
BOILERPLATE_VARIANTS: list[str] = [
    "Crea el script de carga estandar para la tabla {tabla} en el data lake con "
    "las columnas de auditoria habituales (fecha_carga, origen, hash_fila).",
    "Necesito el job de ingesta tipico para {tabla}, con las columnas de control "
    "de siempre: fecha de carga, origen y hash de fila.",
    "Genera el pipeline de carga al data lake de {tabla} anadiendo nuestras "
    "columnas de auditoria estandar (fecha_carga, origen, hash_fila).",
    "Monta el cargador habitual de {tabla} con los campos de auditoria que usamos "
    "siempre: fecha_carga, origen y hash_fila.",
    "Dame el script de siempre para subir {tabla} al lake con fecha_carga, origen "
    "y hash_fila como columnas de control.",
    "Plantilla de ingesta para {tabla} en el data lake, con las columnas de "
    "auditoria de costumbre (fecha_carga, origen, hash_fila).",
    "Quiero el proceso estandar de carga de {tabla} incluyendo las columnas de "
    "auditoria fecha_carga, origen y hash_fila.",
    "Prepara el job de carga tipico de {tabla} al lake con los campos de control "
    "fecha_carga, origen y hash_fila.",
]

BOILERPLATE_RESPONSE = (
    "Script de ingesta al data lake con columnas de auditoria fecha_carga, "
    "origen y hash_fila."
)


# ---------------------------------------------------------------------------
# Escenario: fugas de secretos (Plataforma)
# ---------------------------------------------------------------------------
# Prompts de debug aparentemente inocentes que llevan un secreto real enterrado.
# El campo gt_secret_type permite validar precision y recall de los detectores.
SECRET_LEAK_PROMPTS: list[dict[str, str]] = [
    {
        "prompt_text": (
            "No me conecta el job a la base. Esta es mi cadena, que esta mal: "
            "postgres://svc_pagos:Pr0dPass2026@db-prod.internal:5432/ledger "
            "Dame el fix del timeout."
        ),
        "response_summary": "Revision de parametros de conexion y timeout.",
        "gt_secret_type": "connection_string",
    },
    {
        "prompt_text": (
            "El despliegue falla autenticando. Por si acaso, la clave admin es "
            "verano2024 y el usuario es deploy_bot. Por que rechaza el login."
        ),
        "response_summary": "Analisis del fallo de autenticacion en despliegue.",
        "gt_secret_type": "password",
    },
    {
        "prompt_text": (
            "Necesito que el cliente llame a la API con esta key: "
            "sk-live-9f3aK2mN7pQ8rT1uV4wX6yZ0bC5dE2fG, pero me da 401. "
            "Que estoy haciendo mal en la cabecera."
        ),
        "response_summary": "Diagnostico de cabecera de autorizacion.",
        "gt_secret_type": "api_key",
    },
    {
        "prompt_text": (
            "Mira mi config de AWS, el acceso no va: "
            "AWS_ACCESS_KEY_ID=AKIA4XEXAMPLE12345Z y la secret la pongo en el env. "
            "Como depuro el permiso denegado del bucket."
        ),
        "response_summary": "Revision de credenciales y permisos de bucket.",
        "gt_secret_type": "api_key",
    },
    {
        "prompt_text": (
            "Token de servicio para el webhook: "
            # Se ensambla en ejecucion para probar el detector sin dejar una
            # credencial con forma de GitHub PAT literal en el repositorio.
            + "".join(("gh", "p_AbCdEf1234567890ZyXwVuTsRqPoNmLkJiHgFe"))
            + " . No dispara, ayuda."
        ),
        "response_summary": "Analisis de la entrega del webhook.",
        "gt_secret_type": "api_key",
    },
]
