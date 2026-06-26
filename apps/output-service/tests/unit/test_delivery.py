"""Decisión de entrega según la ventana de 24h (ADR componente 1)."""
from output_service.domain.delivery import choose_delivery
from output_service.domain.models import DeliveryMode


def test_within_window_is_text():
    assert choose_delivery(within_window=True) is DeliveryMode.TEXT


def test_outside_window_is_template():
    assert choose_delivery(within_window=False) is DeliveryMode.TEMPLATE
