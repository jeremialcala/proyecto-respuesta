"""Políticas por `purpose` y generación de tokens opacos. ADR-0017 (design §2).

Cada propósito fija valores por defecto de TTL, `max_uses` y `audience` (recalibrar — ADR-0017
§Pendiente). El emisor puede override-ar `ttl_s`/`max_uses` por caso (p. ej. `max_uses=1` estricto).
El `token_id` es 128-bit aleatorio (anti-enumeración) en base64url sin relleno.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from .models import Audience, Purpose

_TOKEN_BYTES = 16  # 128 bits (design §7, anti-enumeración)


@dataclass(frozen=True)
class GrantPolicy:
    """Valores por defecto de una concesión según su propósito."""
    ttl_s: int
    max_uses: int
    audience: Audience


# Valores iniciales sugeridos en design §2 (tabla purpose/audience/TTL/max_uses).
PURPOSE_POLICIES: dict[Purpose, GrantPolicy] = {
    Purpose.DISAMBIGUATION_CROP: GrantPolicy(ttl_s=600, max_uses=3, audience=Audience.META_FETCHERS),
    Purpose.REPORT_PHOTO:        GrantPolicy(ttl_s=900, max_uses=10, audience=Audience.AUTHENTICATED_SESSION),
    Purpose.PROOF_OF_LIFE:       GrantPolicy(ttl_s=600, max_uses=3, audience=Audience.META_FETCHERS),
    Purpose.ATTACHMENT:          GrantPolicy(ttl_s=600, max_uses=3, audience=Audience.META_FETCHERS),
}


def policy_for(purpose: Purpose) -> GrantPolicy:
    """Política por defecto del propósito. KeyError es un bug de programación, no entrada externa."""
    return PURPOSE_POLICIES[purpose]


def new_token_id() -> str:
    """`token_id` opaco de 128 bits en base64url sin relleno (forma el path /m/{token})."""
    return secrets.token_urlsafe(_TOKEN_BYTES)
