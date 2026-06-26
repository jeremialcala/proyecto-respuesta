"""Decisión de entrega según la ventana de servicio de WhatsApp (ADR componente 1). Puro.

Dentro de la ventana de 24h (hubo mensaje del usuario hace <24h) se puede enviar **texto libre**;
fuera de ella, Meta exige una **plantilla HSM aprobada**. Es una invariante de cumplimiento de Meta.
"""
from __future__ import annotations

from .models import DeliveryMode


def choose_delivery(*, within_window: bool) -> DeliveryMode:
    return DeliveryMode.TEXT if within_window else DeliveryMode.TEMPLATE
