"""Ledger de concesiones en Postgres (sa-east-1). Autoridad del estado. `psycopg` perezoso (ADR-0017).

El `consume` es **atómico** (UPDATE … WHERE used_count < max_uses AND no revocado AND no expirado
RETURNING) para que la multi-descarga de Meta no exceda `max_uses` por carreras. Esqueleto fase 03.

Nota: `report_id`/`entity_id` se almacenan para la revocación en lote al purgar (ADR-0016); el
`grant_service.issue` los poblará cuando el emisor los provea (fuera del alcance del scaffolding).
"""
from __future__ import annotations

from ..domain.models import Audience, Grant, Purpose

_DDL = """
CREATE TABLE IF NOT EXISTS grants (
  token_id text PRIMARY KEY,
  media_ref text NOT NULL,
  audience text NOT NULL,
  purpose text NOT NULL,
  content_type text NOT NULL,
  max_uses int NOT NULL,
  used_count int NOT NULL DEFAULT 0,
  expires_at bigint NOT NULL,
  revoked_at bigint,
  created_by text NOT NULL,
  created_at bigint NOT NULL,
  report_id text,
  entity_id text
);
CREATE INDEX IF NOT EXISTS grants_media_ref_idx ON grants (media_ref);
CREATE INDEX IF NOT EXISTS grants_expires_at_idx ON grants (expires_at);
"""

_COLS = ("token_id", "media_ref", "audience", "purpose", "content_type", "max_uses",
         "used_count", "expires_at", "revoked_at", "created_by", "created_at")


class PgGrantStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    def _c(self):
        if self._conn is None:
            import psycopg
            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def init_schema(self) -> None:
        self._c().execute(_DDL)

    def create(self, grant: Grant) -> None:
        self._c().execute(
            "INSERT INTO grants (token_id, media_ref, audience, purpose, content_type, max_uses,"
            " used_count, expires_at, revoked_at, created_by, created_at)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (grant.token_id, grant.media_ref, grant.audience.value, grant.purpose.value,
             grant.content_type, grant.max_uses, grant.used_count, grant.expires_at,
             grant.revoked_at, grant.created_by, grant.created_at))

    def get(self, token_id: str) -> Grant | None:
        cur = self._c().execute(
            f"SELECT {', '.join(_COLS)} FROM grants WHERE token_id=%s", (token_id,))
        row = cur.fetchone()
        return self._row_to_grant(row) if row else None

    def consume(self, token_id: str) -> bool:
        import time
        cur = self._c().execute(
            "UPDATE grants SET used_count = used_count + 1"
            " WHERE token_id=%s AND revoked_at IS NULL AND expires_at > %s AND used_count < max_uses"
            " RETURNING used_count",
            (token_id, int(time.time())))
        return cur.fetchone() is not None

    def revoke(self, token_id: str) -> None:
        import time
        self._c().execute(
            "UPDATE grants SET revoked_at=%s WHERE token_id=%s AND revoked_at IS NULL",
            (int(time.time()), token_id))

    def revoke_by_ref(self, *, media_ref: str | None = None, report_id: str | None = None,
                      entity_id: str | None = None) -> int:
        import time
        col, val = self._ref_filter(media_ref, report_id, entity_id)
        cur = self._c().execute(
            f"UPDATE grants SET revoked_at=%s WHERE {col}=%s AND revoked_at IS NULL",
            (int(time.time()), val))
        return cur.rowcount

    def purge_expired(self, now_iso: str) -> int:
        import time
        cur = self._c().execute("DELETE FROM grants WHERE expires_at <= %s", (int(time.time()),))
        return cur.rowcount

    @staticmethod
    def _ref_filter(media_ref, report_id, entity_id) -> tuple[str, str]:
        for col, val in (("media_ref", media_ref), ("report_id", report_id), ("entity_id", entity_id)):
            if val is not None:
                return col, val
        raise ValueError("revoke_by_ref requiere media_ref, report_id o entity_id")

    @staticmethod
    def _row_to_grant(row) -> Grant:
        (token_id, media_ref, audience, purpose, content_type, max_uses, used_count,
         expires_at, revoked_at, created_by, created_at) = row
        return Grant(
            token_id=token_id, media_ref=media_ref, audience=Audience(audience),
            purpose=Purpose(purpose), content_type=content_type, max_uses=max_uses,
            expires_at=expires_at, created_by=created_by, created_at=created_at,
            used_count=used_count, revoked_at=revoked_at)
