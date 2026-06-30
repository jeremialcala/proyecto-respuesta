"""Modelo de dominio del media-gateway: la **concesión** (`grant`). ADR-0017 (design §2).

Una concesión autoriza **un** `media_ref` por **una** ventana corta: es la unidad de control. El
`token` que viaja en la URL pública es **opaco** (`token_id` aleatorio + HMAC), nunca contiene el
`media_ref` ni PII. El estado autoritativo (`used_count`, `revoked_at`, `expires_at`) vive en el
ledger (Postgres); el HMAC solo permite descartar basura sin tocar la BD.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Audience(str, Enum):
    """Quién puede descargar la URL. Determina la validación del plano público (design §3)."""
    META_FETCHERS = "meta_fetchers"               # restringe por rango IP / User-Agent de Meta
    AUTHENTICATED_SESSION = "authenticated_session"  # navegador del back office (sesión Auth0, ADR-0009)
    OPEN_TOKEN = "open_token"                      # solo el token opaco protege (uso acotado)


class Purpose(str, Enum):
    """Para qué se emite la concesión; selecciona la política (TTL/max_uses/audience) en policy.py."""
    DISAMBIGUATION_CROP = "disambiguation_crop"   # rostro candidato en el chat (ADR-0016)
    REPORT_PHOTO = "report_photo"                 # foto del desaparecido en el back office
    PROOF_OF_LIFE = "proof_of_life"               # prueba de vida (video)
    ATTACHMENT = "attachment"                     # cualquier adjunto genérico
    ENROLLMENT_CLOSING = "enrollment_closing"     # foto del reporte en el cierre tipo imagen (ADR-0020)


class ServeResult(str, Enum):
    """Resultado tipado de `delivery_service.serve()`; la API lo mapea a HTTP (design §3)."""
    OK = "ok"                     # 200 — bytes descifrados
    FORBIDDEN = "forbidden"       # 403 — allowlist falla o concesión revocada
    NOT_FOUND = "not_found"       # 404 — token inexistente o HMAC inválido (indistinguible)
    GONE = "gone"                 # 410 — expirado o usos agotados
    RATE_LIMITED = "rate_limited" # 429 — rate-limit superado


@dataclass(frozen=True)
class Grant:
    """Una concesión en el ledger. `token` público = base64url(token_id) firmado con HMAC(exp)."""
    token_id: str           # 128-bit aleatorio (base64url) → forma el path /m/{token}
    media_ref: str          # s3://bucket/media/{subject}/{id} — NUNCA viaja en la URL
    audience: Audience
    purpose: Purpose
    content_type: str       # image/jpeg | image/png | video/mp4 …
    max_uses: int           # N pequeño → tolera la multi-descarga de Meta (design §2)
    expires_at: int         # epoch segundos (TTL corto)
    created_by: str         # servicio emisor (output-service/chatbot-gateway/back-office)
    created_at: int         # epoch segundos
    used_count: int = 0     # contador (autoridad: ledger)
    revoked_at: int | None = None  # None | epoch segundos
    # Referencias de negocio para la revocación en lote al purgar (ADR-0016 §6). Opcionales: el token
    # nunca las expone; solo permiten `revoke_by_ref` por reporte/entidad.
    report_id: str | None = None
    entity_id: str | None = None

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: int) -> bool:
        return now >= self.expires_at

    def is_exhausted(self) -> bool:
        return self.used_count >= self.max_uses
