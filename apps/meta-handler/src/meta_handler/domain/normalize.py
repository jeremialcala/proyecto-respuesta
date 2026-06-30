"""Normalización del payload crudo de Meta (ADR-0005). Puro (stdlib).

Entrada: el `raw` que el Webhook Gateway publicó en `meta.received` (el cuerpo tal cual de Meta).
Salida: lista de `NormalizedMessage`. El MVP soporta WhatsApp con tipos **text / image / location** y
las **respuestas interactivas** (botón/lista) que el reportante toca al desambiguar rostros (ADR-0016):
se aplanan a TEXT con el título de la opción, para que el chatbot las resuelva como un texto normal
(`parse_selection`). Otros tipos se marcan `UNSUPPORTED` (se registran y se descartan, no rompen el lote).
"""
from __future__ import annotations

from typing import Optional

from .models import Channel, GeoLocation, MessageType, NormalizedMessage, OBJECT_TO_CHANNEL


def _msg_type(raw_type: str) -> MessageType:
    return {
        "text": MessageType.TEXT,
        "image": MessageType.IMAGE,
        "location": MessageType.LOCATION,
    }.get(raw_type, MessageType.UNSUPPORTED)


def _interactive_text(msg: dict) -> Optional[str]:
    """Título de la opción tocada en una respuesta interactiva (button_reply/list_reply); fallback id."""
    inter = msg.get("interactive", {}) or {}
    reply = inter.get(inter.get("type", ""), {}) or {}   # interactive[interactive.type]
    return reply.get("title") or reply.get("id")


def _normalize_one(channel: Channel, msg: dict) -> NormalizedMessage:
    mid = str(msg.get("id", ""))
    contact = str(msg.get("from", ""))
    raw_type = str(msg.get("type", ""))
    # La respuesta a un botón/lista llega como `interactive`; se aplana a TEXT con el título tocado.
    mtype = MessageType.TEXT if raw_type == "interactive" else _msg_type(raw_type)
    text = None
    media_id = None
    mime = None
    loc = None
    if raw_type == "interactive":
        text = _interactive_text(msg)
    elif mtype is MessageType.TEXT:
        text = (msg.get("text", {}) or {}).get("body")
    elif mtype is MessageType.IMAGE:
        img = msg.get("image", {}) or {}
        media_id = img.get("id")
        mime = img.get("mime_type")
        text = img.get("caption")   # el reportante suele escribir el reporte como PIE DE FOTO
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
