"""Modelos de dominio del Servicio de Salida."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DeliveryMode(Enum):
    TEXT = "text"          # mensaje libre dentro de la ventana de servicio de 24h
    TEMPLATE = "template"  # plantilla HSM aprobada (fuera de la ventana) — componente 1
    INTERACTIVE = "interactive"  # imágenes + botón de opciones (desambiguación multi-rostro, ADR-0016)
    IMAGE = "image"        # un mensaje de tipo imagen (foto + caption) — cierre de enrolamiento (ADR-0020)


@dataclass(frozen=True)
class OutboundReply:
    bot_id: str
    channel: str            # whatsapp (MVP)
    contact_ref: str        # waId destinatario
    text: str               # contenido a entregar (en MVP, texto plano); en kind=image es el caption
    event_id: Optional[str] = None
    # Desambiguación multi-rostro (ADR-0016): miniaturas a mostrar (crop_refs de la bóveda) y el reporte
    # al que pertenecen (etiqueta las concesiones del media-gateway para revocarlas al purgar, §6).
    media_refs: tuple[str, ...] = ()
    report_id: Optional[str] = None
    # Cierre tipo imagen (ADR-0020): una sola foto (media_ref en bóveda) servida por URL firmada + caption.
    kind: str = "text"               # "text" | "image"
    media_ref: Optional[str] = None  # solo kind=image: puntero en bóveda de la foto del reporte
