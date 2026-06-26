"""Rieles de guardarraíles del chatbot (ADR-0002). Heurísticos puros (primera línea, barata).

Política (ADR-0002): bloquear jailbreak / instrucciones embebidas / exfiltración de datos de otros
reportes; mantener tono cordial; no tolerar insultos del interlocutor. Esta capa es la heurística
barata; los rieles NeMo con LLM (self-check) se reservan para caminos de mayor riesgo (port aparte).
"""
from __future__ import annotations

import re

from .models import InputCategory, InputScreen, OutputCategory, OutputScreen

# Patrones de prompt-injection / jailbreak (ES + EN), no exhaustivos.
_INJECTION = [
    r"ignora( todas)?\s+(las\s+)?instrucciones",
    r"olvida (tus|las) instrucciones",
    r"ignore (all )?(previous|prior) instructions",
    r"system prompt|prompt del sistema",
    r"act(ú|u)a como|pretend to be|you are now|eres ahora",
    r"\bDAN\b|jailbreak|modo desarrollador|developer mode",
    r"(revela|muestra|dame).{0,30}(otros|todos los|los dem(á|a)s)\s+reportes",
    r"(exfiltra|extrae|dump).{0,20}(datos|base de datos|reportes)",
]
_ABUSE = [r"\b(idiota|imb(é|e)cil|est(ú|u)pid[oa]|mierda|maldito)\b"]
# Marcadores de fuga / intento de acción en la SALIDA del LLM.
_OUTPUT_LEAK = [
    r"BEGIN (PRIVATE|RSA)|password|contrase(ñ|n)a",
    r"\b(DROP TABLE|DELETE FROM|UPDATE .* SET)\b",
    r"(otros|todos los)\s+reportes\b",
]

_inj = [re.compile(p, re.IGNORECASE) for p in _INJECTION]
_ab = [re.compile(p, re.IGNORECASE) for p in _ABUSE]
_leak = [re.compile(p, re.IGNORECASE) for p in _OUTPUT_LEAK]


def screen_input(text: str) -> InputScreen:
    """Clasifica el mensaje entrante. INJECTION bloquea; ABUSE solo se marca (respuesta cordial)."""
    t = text or ""
    for rx in _inj:
        if rx.search(t):
            return InputScreen(InputCategory.INJECTION, rx.pattern)
    for rx in _ab:
        if rx.search(t):
            return InputScreen(InputCategory.ABUSE, rx.pattern)
    return InputScreen(InputCategory.OK)


def screen_output(reply: str) -> OutputScreen:
    """Valida la salida del LLM: sin fuga de datos ni intentos de acción (ADR-0002)."""
    r = reply or ""
    if not r.strip():
        return OutputScreen(OutputCategory.MALFORMED, "respuesta vacía")
    for rx in _leak:
        if rx.search(r):
            return OutputScreen(OutputCategory.LEAK, rx.pattern)
    return OutputScreen(OutputCategory.OK)
