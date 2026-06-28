"""Servicio del plano público: sirve un medio bajo concesión verificada. ADR-0017 (design §3/§5).

Orquestación **fail-closed**: cualquier paso que falle corta la entrega. El token de la URL es opaco
(`{token_id}.{exp}.{sig}`); el `token_id` ata el token a un único `media_ref` en el ledger, así que la
URL nunca contiene el `media_ref` ni PII. Solo se sirven objetos con `scan=clean`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..domain.models import ServeResult
from . import events
from .ports import AuditLog, EnvelopeCipher, FetcherAllowlist, GrantStore, MediaStore, RateLimiter, TokenSigner


@dataclass(frozen=True)
class DeliveryOutcome:
    """Resultado de `serve()`. La API mapea `result` a HTTP (200/403/404/410/429)."""
    result: ServeResult
    body: bytes | None = None
    content_type: str | None = None


def _parse_token(token: str) -> tuple[str, int, str] | None:
    """`{token_id}.{exp}.{sig}` → (token_id, exp, sig). None si está malformado (→ 404)."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    token_id, exp_raw, sig = parts
    if not token_id or not sig:
        return None
    try:
        exp = int(exp_raw)
    except ValueError:
        return None
    return token_id, exp, sig


class DeliveryService:
    def __init__(self, grants: GrantStore, signer: TokenSigner, allowlist: FetcherAllowlist,
                 limiter: RateLimiter, media: MediaStore, cipher: EnvelopeCipher,
                 audit: AuditLog) -> None:
        self._grants = grants
        self._signer = signer
        self._allowlist = allowlist
        self._limiter = limiter
        self._media = media
        self._cipher = cipher
        self._audit = audit

    def serve(self, token: str, *, src_ip: str, user_agent: str,
              now: int | None = None) -> DeliveryOutcome:
        now = int(time.time()) if now is None else now

        parsed = _parse_token(token)
        if parsed is None:
            return DeliveryOutcome(ServeResult.NOT_FOUND)
        token_id, exp, sig = parsed

        # 1. HMAC barato: descarta basura sin tocar la BD. Inválido = 404 indistinguible (anti-enum).
        if not self._signer.verify(token_id, exp, sig):
            return DeliveryOutcome(ServeResult.NOT_FOUND)

        # 2. Ledger (autoridad). Token inexistente = 404 (indistinguible de HMAC inválido).
        grant = self._grants.get(token_id)
        if grant is None:
            return DeliveryOutcome(ServeResult.NOT_FOUND)

        # 3. Concesión revocada = 403 (design §3).
        if grant.is_revoked():
            return self._served(ServeResult.FORBIDDEN, token_id, src_ip, 0)

        # 4. Allowlist por audiencia (rangos/UA de Meta, sesión de back office). Falla = 403.
        if not self._allowlist.is_allowed(grant.audience.value, src_ip, user_agent):
            return self._served(ServeResult.FORBIDDEN, token_id, src_ip, 0)

        # 5. Rate-limit por token/IP/global. Excedido = 429.
        if not self._limiter.hit(token_id):
            return self._served(ServeResult.RATE_LIMITED, token_id, src_ip, 0)

        # 6. Consumo atómico del ledger: False si expirado o usos agotados = 410.
        if not self._grants.consume(token_id):
            return self._served(ServeResult.GONE, token_id, src_ip, 0)

        # 7. Lee la bóveda; solo objetos limpios (ADR-0005). No-clean o ausente = fail-closed.
        try:
            ciphertext, metadata = self._media.get(grant.media_ref)
        except KeyError:
            return self._served(ServeResult.NOT_FOUND, token_id, src_ip, 0)
        if metadata.get("scan") != "clean":
            return self._served(ServeResult.FORBIDDEN, token_id, src_ip, 0)

        # 8. Descifrado al vuelo (encryption context del sujeto, ADR-0008).
        plaintext = self._cipher.decrypt(ciphertext, metadata)
        self._served(ServeResult.OK, token_id, src_ip, len(plaintext))
        return DeliveryOutcome(ServeResult.OK, body=plaintext, content_type=grant.content_type)

    def _served(self, result: ServeResult, token_id: str, src_ip: str, num_bytes: int) -> DeliveryOutcome:
        """Audita la descarga (toda descarga se registra, design §7) y devuelve el outcome sin cuerpo."""
        self._audit.record(events.MEDIA_SERVED, {
            "token_id": token_id, "src_ip": src_ip, "bytes": num_bytes, "result": result.value,
        })
        return DeliveryOutcome(result)
