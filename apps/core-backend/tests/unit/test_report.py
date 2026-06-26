"""Validación del núcleo obligatorio del reporte (ADR-0007)."""
from core_backend.domain.report import validate_report


def test_complete_is_ok():
    assert validate_report({"subject_name": "Juan", "id_type": "V", "id_number": "123"}).ok


def test_missing_fields_reported():
    v = validate_report({"subject_name": "Juan"})
    assert not v.ok and set(v.missing) == {"id_type", "id_number"}


def test_blank_counts_as_missing():
    assert not validate_report({"subject_name": " ", "id_type": "V", "id_number": "1"}).ok
