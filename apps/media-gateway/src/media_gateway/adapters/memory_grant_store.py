"""GrantStore in-memory (tests). El real es `pg_grant_store.PgGrantStore` (Postgres)."""
from __future__ import annotations

import time
from dataclasses import replace

from ..domain.models import Grant


class MemoryGrantStore:
    def __init__(self) -> None:
        self._grants: dict[str, Grant] = {}

    def create(self, grant: Grant) -> None:
        self._grants[grant.token_id] = grant

    def get(self, token_id: str) -> Grant | None:
        return self._grants.get(token_id)

    def consume(self, token_id: str) -> bool:
        grant = self._grants.get(token_id)
        now = int(time.time())
        if grant is None or grant.is_revoked() or grant.is_expired(now) or grant.is_exhausted():
            return False
        self._grants[token_id] = replace(grant, used_count=grant.used_count + 1)
        return True

    def revoke(self, token_id: str) -> None:
        grant = self._grants.get(token_id)
        if grant is not None and not grant.is_revoked():
            self._grants[token_id] = replace(grant, revoked_at=int(time.time()))

    def revoke_by_ref(self, *, media_ref: str | None = None, report_id: str | None = None,
                      entity_id: str | None = None) -> int:
        # En memoria solo conocemos `media_ref`; report_id/entity_id los resuelve el ledger real.
        count = 0
        for token_id, grant in list(self._grants.items()):
            if media_ref is not None and grant.media_ref == media_ref and not grant.is_revoked():
                self._grants[token_id] = replace(grant, revoked_at=int(time.time()))
                count += 1
        return count

    def purge_expired(self, now_iso: str) -> int:
        now = int(time.time())
        expired = [tid for tid, g in self._grants.items() if g.is_expired(now)]
        for tid in expired:
            del self._grants[tid]
        return len(expired)
