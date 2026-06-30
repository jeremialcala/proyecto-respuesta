"""Políticas por propósito y generación de tokens (dominio puro). ADR-0017 §2."""
from media_gateway.domain.models import Audience, Purpose
from media_gateway.domain.policy import PURPOSE_POLICIES, new_token_id, policy_for


def test_every_purpose_has_a_policy():
    for purpose in Purpose:
        assert purpose in PURPOSE_POLICIES


def test_disambiguation_crop_defaults_match_design():
    pol = policy_for(Purpose.DISAMBIGUATION_CROP)
    assert pol.ttl_s == 600
    assert pol.max_uses == 3                      # N bajo, tolera multi-descarga de Meta
    assert pol.audience is Audience.META_FETCHERS


def test_report_photo_targets_back_office_session():
    pol = policy_for(Purpose.REPORT_PHOTO)
    assert pol.audience is Audience.AUTHENTICATED_SESSION


def test_enrollment_closing_is_served_to_meta_fetchers():
    # ADR-0020: la foto del cierre la descarga Meta al renderizar el image message → META_FETCHERS.
    pol = policy_for(Purpose.ENROLLMENT_CLOSING)
    assert pol.audience is Audience.META_FETCHERS


def test_token_id_is_opaque_and_unique():
    a, b = new_token_id(), new_token_id()
    assert a != b
    assert "/" not in a and "+" not in a and "=" not in a   # base64url sin relleno
    assert len(a) >= 20                                      # ~128 bits
