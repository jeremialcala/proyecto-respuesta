"""Interpretación de la respuesta del reportante a la desambiguación multi-rostro (ADR-0016). Puro.

El usuario ve N miniaturas numeradas (1..N) y responde con el número del rostro que es la persona, o
indica que ninguno lo es. Esta función traduce su texto libre a una decisión: índice 0-based,
`none_of_these`, o inválido (para re-preguntar). No depende de infraestructura.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_NONE_PATTERNS = [
    r"\bningun[oa]s?\b", r"\bnadie\b", r"\bno\s+(es|est[áa]|aparece|sale|son)\b",
    r"\bno\s+es\s+ningun", r"\bnone\b",
]
_none = [re.compile(p, re.IGNORECASE) for p in _NONE_PATTERNS]
_FIRST_INT = re.compile(r"\d+")


@dataclass(frozen=True)
class Selection:
    kind: str          # "index" | "none" | "invalid"
    index: int = -1    # 0-based, válido solo si kind == "index"


def parse_selection(text: str, n_faces: int) -> Selection:
    t = (text or "").strip()
    if not t:
        return Selection("invalid")
    if any(rx.search(t) for rx in _none):
        return Selection("none")
    m = _FIRST_INT.search(t)
    if m:
        k = int(m.group())
        if 1 <= k <= n_faces:
            return Selection("index", k - 1)   # mostrado 1..N → índice 0-based
    return Selection("invalid")
