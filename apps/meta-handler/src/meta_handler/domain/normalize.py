"""Normalización del payload crudo de Meta (ADR-0005). Puro (stdlib).

Entrada: el `raw` que el Webhook Gateway publicó en `meta.received` (el cuerpo tal cual de Meta).
Salida: lista de `NormalizedMessage`. El MVP soporta WhatsApp con tipos **text / image / location**;
otros tipos se marcan `UNSUPPORTED` (se registran y se descartan, no rompen el lote).
"""
from __future__ import annotations

from .models import Channel, GeoLocation, MessageType, NormalizedMessage, OBJECT_TO_CHANNEL


def _msg_type(raw_type: str) -> MessageType:
    return {
        "text": MessageType.TEXT,
        "image": MessageType.IMAGE,
        "location": MessageType.LOCATION,
    }.get(raw_type, MessageType.UNSUPPORTED)


def _normalize_one(channel: Channel, msg: dict) -> NormalizedMessage:
    mid = str(msg.get("id", ""))
    contact = str(msg.get("from", ""))
    mtype = _msg_type(str(msg.get("type", "")))
    text = None
    media_id = None
    mime = None
    loc = None
    if mtype is MessageType.TEXT:
        text = (msg.get("text", {}) or {}).get("body")
    elif mtype is MessageType.IMAGE:
        img = msg.get("image", {}) or {}
        media_id = img.get("id")
        mime = img.get("mime_type")
    elif mtype is MessageType.LOCATION:
        lc = msg.get("location", {}) or {}
        if "latitude" in lc and "longitude" in lc:
            loc = GeoLocation(
                latitude=float(lc["latitude"]),
                longitude=float(lc["longitude"]),
                address=lc.get("address") or lc.get("name"),
            )
    return NormalizedMessage(
        channel=channel, contact_ref=contact, message_id=mid, type=mtype,
        text=text, media_id=media_id, mime_type=mime, location=loc,
    )


def normalize(raw: dict) -> list[NormalizedMessage]:
    """Extrae y normaliza todos los mensajes de un payload de webhook de Meta."""
    if not isinstance(raw, dict):
        raise ValueError("payload de Meta inválido (no es objeto)")
    channel = OBJECT_TO_CHANNEL.get(str(raw.get("object", "")), Channel.UNKNOWN)
    out: list[NormalizedMessage] = []
    for entry in raw.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                out.append(_normalize_one(channel, msg))
    return out
