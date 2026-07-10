"""Deteccion de PII y datos sensibles (determinista, con checksum).

Decision de diseno, en linea con el resto del proyecto: usar la herramienta
donde la herramienta es mejor. La PII estructurada (IBAN, DNI/NIE, tarjeta) NO
se detecta con un LLM: se detecta con una regex y se CONFIRMA con su digito de
control (mod-97 para el IBAN, letra para el DNI, Luhn para la tarjeta). El
checksum es justo lo que un LLM no puede calcular de forma fiable, y es lo que
elimina los falsos positivos: una cadena con pinta de IBAN que no cuadra el
mod-97 no se marca.

El LLM se reserva para lo que no tiene patron: PII descrita en lenguaje natural
(secrets_llm). Aqui no metemos el LLM con calzador.

Para no exponer el dato, las coincidencias se devuelven enmascaradas.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Validadores con digito de control
# ---------------------------------------------------------------------------
def iban_valid(candidate: str) -> bool:
    """Valida un IBAN por el algoritmo mod-97 (ISO 13616)."""
    s = candidate.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    # Cada letra pasa a numero: A=10 ... Z=35. int(c, 36) lo hace para alfanumerico.
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def dni_valid(candidate: str) -> bool:
    """Valida un DNI o NIE espanol por su letra de control."""
    dni = candidate.upper()
    if not re.fullmatch(r"[XYZ]?\d{7,8}[A-Z]", dni):
        return False
    body, letter = dni[:-1], dni[-1]
    if body[0] in "XYZ":  # NIE: X->0, Y->1, Z->2
        body = str("XYZ".index(body[0])) + body[1:]
    if not body.isdigit():
        return False
    return _DNI_LETTERS[int(body) % 23] == letter


def luhn_valid(number: str) -> bool:
    """Valida un numero de tarjeta por el algoritmo de Luhn."""
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    last = len(digits) - 1
    for i, d in enumerate(digits):
        # Se dobla cada segundo digito contando desde la derecha, sin tocar el
        # digito de control (el ultimo). Es decir, posicion par desde la derecha.
        if (last - i) % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# ---------------------------------------------------------------------------
# Enmascarado (no exponer el dato detectado)
# ---------------------------------------------------------------------------
def _mask(value: str, keep: int = 4) -> str:
    compact = value.replace(" ", "")
    if len(compact) <= keep:
        return "*" * len(compact)
    return "*" * (len(compact) - keep) + compact[-keep:]


# ---------------------------------------------------------------------------
# Deteccion
# ---------------------------------------------------------------------------
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,30}\b")
_DNI_RE = re.compile(r"\b[XYZ]?\d{7,8}[A-Za-z]\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _shrink_right(value: str, valid) -> str | None:
    """Recorta tokens por la derecha hasta que el candidato pase el checksum.

    Devuelve el candidato valido mas largo, o None si ningun recorte valida.
    """
    cand = value.rstrip(" -")
    while cand:
        if valid(cand):
            return cand
        cut = max(cand.rfind(" "), cand.rfind("-"))
        if cut == -1:
            return None
        cand = cand[:cut].rstrip(" -")
    return None


def detect_pii(text: str) -> list[dict]:
    """Devuelve la lista de PII detectada y CONFIRMADA por checksum.

    Cada elemento: {"type", "valor" (enmascarado)}. Solo se incluye lo que pasa
    su digito de control; lo que no cuadra se descarta (cero falsos positivos).

    Un fragmento contenido en un dato ya detectado no es una PII aparte: una
    sub-tirada de digitos del cuerpo de un IBAN no es una tarjeta, y el DNI que
    forma la parte local de un email no es un DNI suelto. Por eso fijamos primero
    los spans de lo mas especifico (IBAN, email) y descartamos las coincidencias
    posteriores que caigan dentro de ellos.
    """
    findings: list[dict] = []
    spans: list[tuple[int, int]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, start: int, end: int, value: str) -> None:
        if any(start < b and end > a for a, b in spans):  # solapa algo ya aceptado
            return
        # El span se registra aunque el valor este repetido: una segunda
        # ocurrencia del mismo email debe seguir bloqueando el DNI de su parte
        # local, aunque el hallazgo no se cuente dos veces.
        spans.append((start, end))
        key = (kind, value.replace(" ", ""))
        if key in seen:
            return
        seen.add(key)
        findings.append({"type": kind, "valor": _mask(value)})

    def scan(regex: re.Pattern, kind: str, valid) -> None:
        # La regex es codiciosa y puede engullir tokens posteriores (un importe,
        # un BIC, otro IBAN). Si el match completo no valida, se recorta token a
        # token por la derecha y se revalida; al aceptar un candidato, el resto
        # del texto se vuelve a escanear desde su final.
        pos = 0
        while True:
            m = regex.search(text, pos)
            if not m:
                break
            cand = _shrink_right(m.group(), valid)
            if cand is None:
                pos = m.end()
                continue
            start = m.start()
            add(kind, start, start + len(cand), cand)
            pos = start + len(cand)

    scan(_IBAN_RE, "iban", iban_valid)
    for m in _EMAIL_RE.finditer(text):
        add("email", m.start(), m.end(), m.group())
    for m in _DNI_RE.finditer(text):
        if dni_valid(m.group()):
            add("dni", m.start(), m.end(), m.group())
    scan(_CARD_RE, "tarjeta", luhn_valid)

    return findings


def has_pii(text: str) -> bool:
    return bool(detect_pii(text))
