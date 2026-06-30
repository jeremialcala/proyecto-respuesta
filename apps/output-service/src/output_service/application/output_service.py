"""Caso de uso del Servicio de Salida (ADR-0005): entrega la respuesta al usuario por la Graph API.

Consume `outbound.reply`, descifra el cuerpo, decide el modo de entrega según la **ventana de 24h**
(texto libre dentro; plantilla HSM fuera) y envía por la red correspondiente. Idempotencia por
`event_id` aguas arriba; fallo → no se borra el mensaje (redrive a DLQ, ADR-0012).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import OutputConfig
from ..domain.delivery import choose_delivery
from ..domain.face_options import build_face_options, use_buttons
from ..domain.models import DeliveryMode, OutboundReply
from .ports import BodyCipher, EventLog, MediaGrantClient, MetaSender, WindowStore

# Concesión de medios para mostrar rostros en el chat (ADR-0016 §6 / ADR-0017).
_DISAMBIGUATION_PURPOSE = "disambiguation_crop"
_CROP_CONTENT_TYPE = "image/jpeg"   # los recortes de rostro se guardan como JPEG
# Cierre de enrolamiento con la foto del reporte (ADR-0020 RF-18).
_CLOSING_PURPOSE = "enrollment_closing"

log = logging.getLogger(__name__)


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
        media_refs=tuple(p.get("media_refs", ()) or ()),
        report_id=p.get("report_id"),
        kind=p.get("kind", "text"),
        media_ref=(p.get("media") or {}).get("media_ref") or p.get("media_ref"),
    )


class OutputService:
    def __init__(self, cfg: OutputConfig, cipher: BodyCipher, window: WindowStore,
                 sender: MetaSender, event_log: EventLog,
                 grants: MediaGrantClient | None = None) -> None:
        self._cfg = cfg
        self._cipher = cipher
        self._window = window
        self._sender = sender
        self._log = event_log
        self._grants = grants   # opcional: solo se usa para la desambiguación con miniaturas

    def handle(self, outbound_reply_envelope: dict) -> SendResult:
        reply = _parse(outbound_reply_envelope, self._cipher)
        within_window = self._window.is_open(reply.contact_ref)

        # Desambiguación multi-rostro (ADR-0016): mostrar las miniaturas + botón de opciones. Requiere
        # ventana abierta (imagen/interactivo son texto libre para Meta) y el cliente de concesiones.
        if reply.media_refs and within_window and self._grants is not None:
            self._send_face_selection(reply)
            self._log.record_action(reply.event_id or "", "outbound",
                                    DeliveryMode.INTERACTIVE.value, reply.contact_ref)
            return SendResult(DeliveryMode.INTERACTIVE)

        # Cierre tipo imagen (ADR-0020): la foto del reporte por URL firmada + el resumen como caption.
        # Requiere ventana abierta (image message es texto libre para Meta). Si no se puede servir la
        # imagen (sin media-gateway o falla la concesión), el resumen igual llega como TEXTO: la imagen
        # exige el plano público del media-gateway alcanzable por Meta (ADR-0017), no aplica en localhost.
        if reply.kind == "image" and reply.media_ref and within_window:
            link = None
            if self._grants is not None:
                try:
                    link = self._grants.issue_grant(
                        reply.media_ref, content_type=_CROP_CONTENT_TYPE, purpose=_CLOSING_PURPOSE,
                        channel=reply.channel, report_id=reply.report_id)
                except Exception:
                    log.warning("concesión de imagen de cierre falló; degrado a texto", exc_info=True)
            if link:
                self._sender.send_image(reply.bot_id, reply.channel, reply.contact_ref, link, reply.text)
                self._log.record_action(reply.event_id or "", "outbound", DeliveryMode.IMAGE.value,
                                        reply.contact_ref)
                return SendResult(DeliveryMode.IMAGE)
            self._sender.send_text(reply.bot_id, reply.channel, reply.contact_ref, reply.text)
            self._log.record_action(reply.event_id or "", "outbound", DeliveryMode.TEXT.value,
                                    reply.contact_ref)
            return SendResult(DeliveryMode.TEXT)

        mode = choose_delivery(within_window=within_window)
        if mode is DeliveryMode.TEXT:
            self._sender.send_text(reply.bot_id, reply.channel, reply.contact_ref, reply.text)
        else:
            # Fuera de la ventana: solo la plantilla HSM aprobada (el texto libre lo rechaza Meta).
            self._sender.send_template(reply.bot_id, reply.channel, reply.contact_ref,
                                       self._cfg.hsm_template, self._cfg.hsm_lang)
        self._log.record_action(reply.event_id or "", "outbound", mode.value, reply.contact_ref)
        return SendResult(mode)

    def _send_face_selection(self, reply: OutboundReply) -> None:
        """Una imagen por rostro (URL firmada) + un botón de opciones para elegir cuál es la persona."""
        n = len(reply.media_refs)
        for i, crop_ref in enumerate(reply.media_refs):
            link = self._grants.issue_grant(
                crop_ref, content_type=_CROP_CONTENT_TYPE, purpose=_DISAMBIGUATION_PURPOSE,
                channel=reply.channel, report_id=reply.report_id)
            self._sender.send_image(reply.bot_id, reply.channel, reply.contact_ref,
                                    link, f"Rostro {i + 1}")
        options = build_face_options(n)
        rows = [(o.id, o.label) for o in options]
        if use_buttons(n):
            self._sender.send_buttons(reply.bot_id, reply.channel, reply.contact_ref, reply.text, rows)
        else:
            self._sender.send_list(reply.bot_id, reply.channel, reply.contact_ref,
                                   reply.text, "Ver opciones", rows)
