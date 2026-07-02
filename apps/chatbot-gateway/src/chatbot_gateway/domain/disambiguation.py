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


_ALL_INTS = re.compile(r"\d+")
_YES_PATTERNS = [r"\btod[oa]s?\b", r"\bs[íi]\b", r"\bambos\b", r"\bl[oa]s\s+dos\b"]
_yes = [re.compile(p, re.IGNORECASE) for p in _YES_PATTERNS]


@dataclass(frozen=True)
class MultiSelection:
    kind: str                    # "indices" | "none" | "all" | "invalid"
    indices: tuple[int, ...] = ()  # 0-based, válido solo si kind == "indices"


def parse_multi_selection(text: str, n_faces: int) -> MultiSelection:
    """Respuesta del reportante a "¿a cuáles de estas personas también reportarás?" (ADR-0021 RF-21).

    Acepta varios números (1..N, en cualquier separador), "ninguno"/"nadie", o "todos". Devuelve los
    índices 0-based únicos y en orden. Sin número válido y sin palabra reconocida → invalid (re-preguntar).
    """
    t = (text or "").strip()
    if not t:
        return MultiSelection("invalid")
    if any(rx.search(t) for rx in _none):
        return MultiSelection("none")
    nums = [int(x) for x in _ALL_INTS.findall(t)]
    valid = [k - 1 for k in dict.fromkeys(nums) if 1 <= k <= n_faces]  # únicos, en orden, 0-based
    if valid:
        return MultiSelection("indices", tuple(valid))
    if any(rx.search(t) for rx in _yes):   # "todos"/"sí" sin números → todos los rostros
        return MultiSelection("all", tuple(range(n_faces)))
    return MultiSelection("invalid")


_YESNO_YES = re.compile(r"\b(s[íi]|claro|correcto|confirmo|acepto|de acuerdo|ok|okay|dale)\b", re.IGNORECASE)
_YESNO_NO = re.compile(r"\b(no|nop|negativo|niego|rechazo|para nada)\b", re.IGNORECASE)


def parse_yes_no(text: str) -> str:
    """Interpreta una respuesta sí/no (consentimiento, ADR-0021). Devuelve 'yes' | 'no' | 'invalid'."""
    t = (text or "").strip()
    if _YESNO_NO.search(t):
        return "no"
    if _YESNO_YES.search(t):
        return "yes"
    return "invalid"
