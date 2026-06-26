"""DEPRECADO — el transporte pasó de AMQP/RabbitMQ a AWS SQS/SNS (ADR-0012).

Usar `sqs_consumer.SqsConsumer` (ingestión) y `sqs_sns_event_bus.SnsEventBus` (publicación).
Este módulo se conserva solo como marcador histórico; no debe usarse.
"""
from __future__ import annotations

_DEPRECATED = True  # ver ADR-0012 (broker AWS SQS/SNS)
