"""Modelos de dominio del Core Backend (charter + ADR-0007)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PersonState(Enum):
    DESAPARECIDO = "desaparecido"
    A_SALVO = "a_salvo"
    LOCALIZADO_ESTABLE = "localizado_estable"
    LOCALIZADO_CRITICO = "localizado_critico"
    FALLECIDO = "fallecido"
    NO_IDENTIFICADO = "no_identificado"


class Mechanism(Enum):
    """Quién mueve el estado (matriz de transiciones del charter)."""
    AUTORREPORTE = "autorreporte"
    RESCATISTA = "rescatista"
    COORDINADOR = "coordinador"
    AUTORIDAD = "autoridad"


class Intention(Enum):
    DESAPARECIDO = "desaparecido"
    ENCONTRADO = "encontrado"
    AUTOREPORTE = "autoreporte"


@dataclass(frozen=True)
class Report:
    """Reporte con esquema dinámico (ADR-0007): núcleo obligatorio + atributos extensibles."""
    intention: str
    subject_name: str
    id_type: Optional[str] = None      # documento opcional: la identidad del sistema es biométrica
    id_number: Optional[str] = None
    attributes: dict = field(default_factory=dict)   # foto/ubicación/notas y futuros, sin migración
