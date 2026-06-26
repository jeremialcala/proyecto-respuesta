"""Caso de uso del Servicio de Salida (ADR-0005): entrega la respuesta al usuario por la Graph API.

Consume `outbound.reply`, descifra el cuerpo, decide el modo de entrega según la **ventana de 24h**
(texto libre dentro; plantilla HSM fuera) y envía por la red correspondiente. Idempotencia por
`event_id` aguas arriba; fallo → no se borra el mensaje (redrive a DLQ, ADR-0012).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import OutputConfig
from ..domain.delivery import choose_delivery
from ..domain.models import DeliveryMode, OutboundReply
from .ports import BodyCipher, EventLog, MetaSender, WindowStore


@dataclass(frozen=True)
class SendResult:
    mode: DeliveryMode


def _parse(envelope: dict, cipher: BodyCipher) -> OutboundReply:
    p = envelope.get("payload", {}) or {}
    return OutboundReply(
        bot_id=p.get("bot_id", ""),
        channel=p.get("channel", "whatsapp"),
        contact_ref=p.get("contact_ref", ""),
        text=cipher.decrypt(p.get("jwe_body", "") or ""),
        event_id=envelope.get("event_id"),
    )


class OutputService:
    def __init__(self, cfg: OutputConfig, cipher: BodyCipher, window: WindowStore,
                 sender: MetaSender, event_log: EventLog) -> None:
        self._cfg = cfg
        self._cipher = cipher
        self._window = window
        self._sender = sender
        self._log = event_log

    def handle(self, outbound_reply_envelope: dict) -> SendResult:
        reply = _parse(outbound_reply_envelope, self._cipher)
        mode = choose_delivery(within_window=self._window.is_open(reply.contact_ref))
        if mode is DeliveryMode.TEXT:
            self._sender.send_text(reply.bot_id, reply.channel, reply.contact_ref, reply.text)
        else:
            # Fuera de la ventana: solo la plantilla HSM aprobada (el texto libre lo rechaza Meta).
            self._sender.send_template(reply.bot_id, reply.channel, reply.contact_ref,
                                       self._cfg.hsm_template, self._cfg.hsm_lang)
        self._log.record_action(reply.event_id or "", "outbound", mode.value, reply.contact_ref)
        return SendResult(mode)
