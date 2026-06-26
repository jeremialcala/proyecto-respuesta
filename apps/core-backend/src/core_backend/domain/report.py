"""Validación del esquema dinámico del reporte (ADR-0007). Puro (stdlib).

Núcleo **obligatorio**: nombre completo, tipo de identificación y número de identificación. El resto
(foto, última ubicación, notas) es opcional y vive en `attributes` sin migración de esquema.
"""
from __future__ import annotations

from dataclasses import dataclass

MANDATORY = ("subject_name", "id_type", "id_number")


@dataclass(frozen=True)
class ReportValidation:
    ok: bool
    missing: tuple[str, ...] = ()


def validate_report(fields: dict) -> ReportValidation:
    missing = tuple(k for k in MANDATORY if not (fields.get(k) or "").strip())
    return ReportValidation(ok=not missing, missing=missing)
