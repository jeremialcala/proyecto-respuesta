"""Modelos de dominio del Servicio de Salida."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DeliveryMode(Enum):
    TEXT = "text"          # mensaje libre dentro de la ventana de servicio de 24h
    TEMPLATE = "template"  # plantilla HSM aprobada (fuera de la ventana) — componente 1
    INTERACTIVE = "interactive"  # imágenes + botón de opciones (desambiguación multi-rostro, ADR-0016)


@dataclass(frozen=True)
class OutboundReply:
    bot_id: str
    channel: str            # whatsapp (MVP)
    contact_ref: str        # waId destinatario
    text: str               # contenido a entregar (en MVP, texto plano)
    event_id: Optional[str] = None
    # Desambiguación multi-rostro (ADR-0016): miniaturas a mostrar (crop_refs de la bóveda) y el reporte
    # al que pertenecen (etiqueta las concesiones del media-gateway para revocarlas al purgar, §6).
    media_refs: tuple[str, ...] = ()
    report_id: Optional[str] = None
