"""Modelos de dominio del Meta Handler."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Channel(Enum):
    WHATSAPP = "whatsapp"
    MESSENGER = "messenger"
    INSTAGRAM = "instagram"
    UNKNOWN = "unknown"


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    LOCATION = "location"
    UNSUPPORTED = "unsupported"   # audio/video/document/sticker… (no en el MVP)


@dataclass(frozen=True)
class GeoLocation:
    latitude: float
    longitude: float
    address: Optional[str] = None


@dataclass(frozen=True)
class NormalizedMessage:
    """Mensaje entrante normalizado, listo para repartir a inbound.text / inbound.media."""
    channel: Channel
    contact_ref: str          # waId / fbId resuelto (sin PII en claro fuera del cuerpo)
    message_id: str
    type: MessageType
    text: Optional[str] = None
    media_id: Optional[str] = None
    mime_type: Optional[str] = None
    location: Optional[GeoLocation] = None


# Mapeo object de Meta → canal lógico (MVP: WhatsApp).
OBJECT_TO_CHANNEL = {
    "whatsapp_business_account": Channel.WHATSAPP,
    "page": Channel.MESSENGER,
    "instagram": Channel.INSTAGRAM,
}
