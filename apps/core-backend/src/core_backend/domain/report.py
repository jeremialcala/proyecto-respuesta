"""Validación del esquema dinámico del reporte (ADR-0007). Puro (stdlib).

Núcleo **obligatorio**: el nombre de la persona. El documento de identidad (tipo + número) es
**opcional** —quien reporta a un tercero rara vez lo tiene y la identidad del sistema es biométrica
(la cara, ADR-0016)—; foto, última ubicación y notas también viven en `attributes` sin migración de
esquema. La "accionabilidad" (nombre + foto o ubicación) se exige en la capa conversacional (chatbot).
"""
from __future__ import annotations

from dataclasses import dataclass

MANDATORY = ("subject_name",)


@dataclass(frozen=True)
class ReportValidation:
    ok: bool
    missing: tuple[str, ...] = ()


def validate_report(fields: dict) -> ReportValidation:
    missing = tuple(k for k in MANDATORY if not (fields.get(k) or "").strip())
    return ReportValidation(ok=not missing, missing=missing)
