"""Sobre común de eventos (ADR-0011). Puro (stdlib). Copia por servicio (refactor a lib: futuro)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

ENVELOPE_VERSION = "1.0.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(event_type: str, payload: dict, producer: str, *,
                   event_id: Optional[str] = None, timestamp: Optional[str] = None,
                   version: str = ENVELOPE_VERSION) -> dict:
    if not event_type:
        raise ValueError("event_type es obligatorio")
    if not producer:
        raise ValueError("producer es obligatorio")
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "producer": producer,
        "timestamp": timestamp or _utc_now_iso(),
        "version": version,
        "payload": payload,
    }
