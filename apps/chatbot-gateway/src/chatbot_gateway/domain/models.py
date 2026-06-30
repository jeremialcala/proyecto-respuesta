"""Modelos de dominio de la Pasarela de Chatbot."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InputCategory(Enum):
    OK = "ok"
    INJECTION = "injection"   # jailbreak / instrucciones embebidas / exfiltración (ADR-0002)
    ABUSE = "abuse"           # insultos del interlocutor → respuesta cordial, sin bloquear el flujo


class OutputCategory(Enum):
    OK = "ok"
    MALFORMED = "malformed"   # el LLM no devolvió la estructura esperada
    LEAK = "leak"             # la salida intenta filtrar datos / ejecutar acciones


@dataclass(frozen=True)
class InputScreen:
    category: InputCategory
    reason: str = ""

    @property
    def blocked(self) -> bool:
        return self.category is InputCategory.INJECTION


@dataclass(frozen=True)
class OutputScreen:
    category: OutputCategory
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.category is OutputCategory.OK


@dataclass(frozen=True)
class ReportDraft:
    """Borrador de reporte extraído por el LLM (no autoritativo). Lo confirma el core-backend."""
    intention: str                       # desaparecido | encontrado | autoreporte
    subject_name: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    notes: Optional[str] = None
    location: Optional[str] = None       # dónde fue visto por última vez (resumen de cierre, ADR-0020)
    complete: bool = False               # ¿tiene el núcleo obligatorio? (nombre + tipo + nº id)
