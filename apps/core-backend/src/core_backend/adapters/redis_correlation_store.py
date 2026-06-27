"""Correlación foto↔reporte por contacto sobre Redis, con TTL (ADR-0016). `redis` perezoso.

La foto (`media.stored`) y el reporte de texto (`report.received`) del mismo contacto pueden llegar en
cualquier orden. Este store recuerda, por `contact_ref` y durante un TTL (alineado con la ventana de
conversación, ADR-0015), el último `media_ref` y los ids del reporte ingerido, para que el lado que
llegue después dispare el enrolamiento. Si Redis no está disponible, degrada a "sin correlación".
"""
from __future__ import annotations

import json
import logging
from typing import Optional

log = logging.getLogger(__name__)


class RedisCorrelationStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 86400, namespace: str = "media:corr") -> None:
        self._url = redis_url
        self._ttl = ttl_seconds
        self._ns = namespace
        self._client = None

    def _ensure(self):
        if self._client is None:
            import redis  # import perezoso
            self._client = redis.Redis.from_url(self._url)
        return self._client

    def _mk(self, kind: str, contact_ref: str) -> str:
        return f"{self._ns}:{kind}:{contact_ref}"

    def remember_media(self, contact_ref: str, media_ref: str) -> None:
        if not contact_ref or not media_ref:
            return
        try:
            self._ensure().setex(self._mk("media", contact_ref), self._ttl, media_ref)
        except Exception:
            log.warning("no se pudo recordar media de %s (Redis no disponible)", contact_ref)

    def get_media(self, contact_ref: str) -> Optional[str]:
        if not contact_ref:
            return None
        try:
            v = self._ensure().get(self._mk("media", contact_ref))
            return v.decode() if v else None
        except Exception:
            return None

    def remember_report(self, contact_ref: str, report_id: str, entity_id: str,
                        reporter: Optional[dict] = None) -> None:
        if not contact_ref:
            return
        record = {"report_id": report_id, "entity_id": entity_id,
                  "bot_id": (reporter or {}).get("bot_id", ""),
                  "channel": (reporter or {}).get("channel", "")}
        try:
            self._ensure().setex(self._mk("report", contact_ref), self._ttl, json.dumps(record))
        except Exception:
            log.warning("no se pudo recordar reporte de %s (Redis no disponible)", contact_ref)

    def get_report(self, contact_ref: str) -> Optional[dict]:
        if not contact_ref:
            return None
        try:
            v = self._ensure().get(self._mk("report", contact_ref))
            return json.loads(v) if v else None
        except Exception:
            return None
