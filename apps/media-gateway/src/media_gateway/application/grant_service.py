"""Servicio del plano interno: emisión y revocación de concesiones. ADR-0017 (design §3/§4).

Lo llaman `output-service`, `chatbot-gateway` y el back office **en el momento de enviar**, para que
el TTL de la URL sea mínimo. No es público (mesh privado, IRSA/mTLS).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..domain.models import Audience, Grant, Purpose
from ..domain.policy import new_token_id, policy_for
from . import events
from .ports import AuditLog, GrantStore, TokenSigner


@dataclass(frozen=True)
class IssuedGrant:
    """Respuesta de `POST /grants` (design §3): la URL firmada + metadatos no sensibles."""
    url: str
    token_id: str
    expires_at: int


class GrantService:
    def __init__(self, store: GrantStore, signer: TokenSigner, audit: AuditLog,
                 public_base_url: str) -> None:
        self._store = store
        self._signer = signer
        self._audit = audit
        self._base = public_base_url.rstrip("/")

    def issue(self, *, media_ref: str, content_type: str, purpose: Purpose, created_by: str,
              audience: Audience | None = None, ttl_s: int | None = None,
              max_uses: int | None = None, report_id: str | None = None,
              entity_id: str | None = None, now: int | None = None) -> IssuedGrant:
        """Emite una concesión sobre `media_ref`. Resuelve la política por `purpose`; el emisor puede
        override-ar `audience`/`ttl_s`/`max_uses` (p. ej. `max_uses=1` estricto). `report_id`/`entity_id`
        etiquetan la concesión para la revocación en lote al purgar (ADR-0016 §6)."""
        pol = policy_for(purpose)
        now = int(time.time()) if now is None else now
        expires_at = now + (ttl_s if ttl_s is not None else pol.ttl_s)
        token_id = new_token_id()
        grant = Grant(
            token_id=token_id,
            media_ref=media_ref,
            audience=audience if audience is not None else pol.audience,
            purpose=purpose,
            content_type=content_type,
            max_uses=max_uses if max_uses is not None else pol.max_uses,
            expires_at=expires_at,
            created_by=created_by,
            created_at=now,
            report_id=report_id,
            entity_id=entity_id,
        )
        self._store.create(grant)
        sig = self._signer.sign(token_id, expires_at)
        url = f"{self._base}/m/{token_id}.{expires_at}.{sig}"
        self._audit.record(events.GRANT_ISSUED, {
            "token_id": token_id, "media_ref": media_ref, "purpose": purpose.value,
            "audience": grant.audience.value, "created_by": created_by, "expires_at": expires_at,
            "report_id": report_id, "entity_id": entity_id,
        })
        return IssuedGrant(url=url, token_id=token_id, expires_at=expires_at)

    def revoke(self, token_id: str) -> None:
        self._store.revoke(token_id)
        self._audit.record(events.GRANT_REVOKED, {"token_id": token_id})

    def revoke_by_ref(self, *, media_ref: str | None = None, report_id: str | None = None,
                      entity_id: str | None = None) -> int:
        count = self._store.revoke_by_ref(media_ref=media_ref, report_id=report_id, entity_id=entity_id)
        self._audit.record(events.GRANT_REVOKED, {
            "media_ref": media_ref, "report_id": report_id, "entity_id": entity_id, "count": count,
        })
        return count
