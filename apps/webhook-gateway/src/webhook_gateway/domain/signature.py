"""Verificación de la firma de Meta `X-Hub-Signature-256` (ADR-0005, threat model T1/T11).

HMAC-SHA256 del **cuerpo crudo** con el app secret. Comparación en tiempo constante. Puro: solo
stdlib, sin dependencias de infraestructura → testeable de forma aislada.
"""
from __future__ import annotations

import hashlib
import hmac

_PREFIX = "sha256="


def compute_signature(app_secret: str, raw_body: bytes) -> str:
    """Firma esperada en el formato del header de Meta (`sha256=<hex>`)."""
    digest = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return _PREFIX + digest


def verify_signature(app_secret: str, raw_body: bytes, header: str | None) -> bool:
    """True si el header coincide con el HMAC del cuerpo. Rechaza header ausente/mal formado."""
    if not header or not header.startswith(_PREFIX):
        return False
    if not app_secret:
        return False
    expected = compute_signature(app_secret, raw_body)
    return hmac.compare_digest(expected, header)
