"""Parse mínimo del webhook de Meta: tipo de `object` e IDs de mensaje para idempotencia.

El Gateway **no normaliza** el contenido (eso es del Meta Handler, ADR-0005); aquí solo se extrae lo
imprescindible para deduplicar (message ids) y para una validación temprana del `object`. Puro
(stdlib). Soporta la forma de WhatsApp (`messages[].id` = `wamid.…`) y, de forma tolerante, la de
Messenger (`messaging[].message.mid`).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetaSummary:
    object_type: str
    message_ids: tuple[str, ...]

    @property
    def dedup_key(self) -> str | None:
        """Clave de deduplicación: el primer message id (Meta reintrega con el mismo id)."""
        return self.message_ids[0] if self.message_ids else None


def summarize(raw: dict) -> MetaSummary:
    """Extrae `object` y los ids de mensaje de un payload de webhook de Meta."""
    if not isinstance(raw, dict):
        raise ValueError("payload de Meta inválido (no es objeto)")
    object_type = str(raw.get("object", ""))
    ids: list[str] = []
    for entry in raw.get("entry", []) or []:
        # WhatsApp / Instagram: entry[].changes[].value.messages[].id
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                mid = msg.get("id")
                if mid:
                    ids.append(str(mid))
        # Messenger: entry[].messaging[].message.mid
        for m in entry.get("messaging", []) or []:
            mid = (m.get("message", {}) or {}).get("mid")
            if mid:
                ids.append(str(mid))
    return MetaSummary(object_type=object_type, message_ids=tuple(ids))
