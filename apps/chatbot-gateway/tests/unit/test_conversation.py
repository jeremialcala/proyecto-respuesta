"""Modelo de perfil de sesión: reset del reporte, detección de sujeto nuevo y persistencia (ADR-0020)."""
from chatbot_gateway.adapters.pg_conversation_store import (_profile_from_json, _profile_to_json)
from chatbot_gateway.domain.conversation import SessionProfile

import json


def test_reset_report_clears_report_but_keeps_identity_and_dedup():
    p = SessionProfile(
        declared_name="María", intention="desaparecido", subject_name="Juan",
        id_type="V", id_number="123", location="Caracas", notes="camisa azul",
        turn_count=7, report_emitted=True, photo_retry_count=2,
        pending_disambiguation_id="dis_1", pending_faces_count=2, last_closed_ref="rep_1")
    r = p.reset_report(last_closed_ref="rep_1")
    # reporte en curso limpio
    assert (r.intention, r.subject_name, r.id_type, r.id_number, r.location, r.notes) == (
        None, None, None, None, None, None)
    assert r.report_emitted is False and r.photo_retry_count == 0
    assert r.pending_disambiguation_id is None and r.pending_faces_count == 0
    # identidad/memoria y dedup preservados
    assert r.declared_name == "María" and r.turn_count == 7 and r.last_closed_ref == "rep_1"


def test_is_new_subject():
    p = SessionProfile(subject_name="Wilfredo Medina")
    assert p.is_new_subject("Anahys Garcia") is True
    assert p.is_new_subject("  wilfredo  medina ".upper()) is False  # mismo (normalizado) → no es nuevo
    assert p.is_new_subject(None) is False
    assert SessionProfile().is_new_subject("Quien sea") is False     # sin sujeto actual → no es nuevo


def test_pg_profile_roundtrip_persists_location_and_dedup():
    """Regresión: `location` y `last_closed_ref` deben sobrevivir el guardado/carga del perfil."""
    p = SessionProfile(subject_name="Ana", location="La Guaira", report_emitted=True,
                       last_closed_ref="rep_9", photo_retry_count=1, turn_count=3)
    back = _profile_from_json(json.loads(_profile_to_json(p)))
    assert back.location == "La Guaira"
    assert back.last_closed_ref == "rep_9"
    assert back.photo_retry_count == 1
    assert back.subject_name == "Ana" and back.report_emitted is True and back.turn_count == 3
