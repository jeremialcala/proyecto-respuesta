"""Validación del núcleo obligatorio del reporte (ADR-0007).

El único campo obligatorio es el nombre. El documento de identidad es opcional (la identidad del
sistema es biométrica, ADR-0016): un reporte sin cédula es válido.
"""
from core_backend.domain.report import validate_report


def test_complete_is_ok():
    assert validate_report({"subject_name": "Juan", "id_type": "V", "id_number": "123"}).ok


def test_name_only_is_ok_document_optional():
    """Sin documento pero con nombre → válido (caso real: se reporta a un tercero sin su cédula)."""
    assert validate_report({"subject_name": "Carmen Suárez"}).ok


def test_missing_name_is_reported():
    v = validate_report({"id_type": "V", "id_number": "123"})
    assert not v.ok and set(v.missing) == {"subject_name"}


def test_blank_name_counts_as_missing():
    assert not validate_report({"subject_name": " ", "id_type": "V", "id_number": "1"}).ok
