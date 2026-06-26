"""Caso de uso de la Pasarela de Chatbot (ADR-0001/0002).

Consume `inbound.text`, descifra, pasa rieles de **entrada**, conversa con el **LLM on-prem**, pasa
rieles de **salida**, publica `outbound.reply` y —si el LLM extrajo un reporte con el núcleo
obligatorio— `report.received`. El LLM **no es autoritativo**: este servicio nunca emite
`state.changed` ni eventos de match; solo conversa y captura.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..config import ChatbotConfig
from ..domain import guardrails
from ..domain.models import InputCategory, ReportDraft
from .events import build_envelope
from .ports import BodyCipher, EventLog, LlmClient, ReplyPublisher, ReportPublisher

_SAFE_BLOCKED = ("Por tu seguridad no puedo procesar ese mensaje. ¿Puedo ayudarte a reportar o "
                 "buscar a una persona?")
_SAFE_FALLBACK = ("Disculpa, tuve un problema procesando tu mensaje. ¿Puedes reformularlo, por favor?")
_CORDIAL_PREFIX = "Entiendo que es un momento difícil. "


class Outcome(Enum):
    REPLIED = "replied"
    REPLIED_WITH_REPORT = "replied_with_report"
    BLOCKED = "blocked"
    OUTPUT_REJECTED = "output_rejected"


@dataclass(frozen=True)
class HandleResult:
    outcome: Outcome


class ChatbotService:
    def __init__(self, cfg: ChatbotConfig, cipher: BodyCipher, llm: LlmClient,
                 reply_pub: ReplyPublisher, report_pub: ReportPublisher, event_log: EventLog) -> None:
        self._cfg = cfg
        self._cipher = cipher
        self._llm = llm
        self._reply = reply_pub
        self._report = report_pub
        self._log = event_log

    def handle(self, inbound_text_envelope: dict) -> HandleResult:
        p = inbound_text_envelope.get("payload", {}) or {}
        event_id = inbound_text_envelope.get("event_id", "")
        bot_id, channel = p.get("bot_id", ""), p.get("channel", "")
        contact_ref = p.get("contact_ref", "")

        body = json.loads(self._cipher.decrypt(p.get("jwe_body", "") or "{}"))
        if body.get("kind") == "location":
            # Ubicación: contexto, no conversación; ack cordial (sin LLM en el MVP).
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                "Recibí tu ubicación, gracias. La sumo al reporte.")
            return HandleResult(Outcome.REPLIED)

        user_text = body.get("text", "")

        # --- riel de entrada ---
        screen = guardrails.screen_input(user_text)
        if screen.blocked:
            self._log.record_action(event_id, "input_rail", "BLOCKED", screen.reason)
            self._publish_reply(bot_id, channel, contact_ref, event_id, _SAFE_BLOCKED)
            return HandleResult(Outcome.BLOCKED)

        # --- LLM (no autoritativo) ---
        reply_text, draft = self._llm.converse(user_text)

        # --- riel de salida ---
        out = guardrails.screen_output(reply_text)
        if not out.ok:
            self._log.record_action(event_id, "output_rail", out.category.value, out.reason)
            self._publish_reply(bot_id, channel, contact_ref, event_id, _SAFE_FALLBACK)
            return HandleResult(Outcome.OUTPUT_REJECTED)

        if screen.category is InputCategory.ABUSE:
            reply_text = _CORDIAL_PREFIX + reply_text   # tono cordial ante insultos (ADR-0002)

        self._publish_reply(bot_id, channel, contact_ref, event_id, reply_text)

        if draft is not None and draft.complete:
            self._publish_report(bot_id, channel, contact_ref, event_id, draft)
            return HandleResult(Outcome.REPLIED_WITH_REPORT)
        return HandleResult(Outcome.REPLIED)

    # --- publicación ---
    def _publish_reply(self, bot_id, channel, contact_ref, event_id, text) -> None:
        self._reply.publish_reply(build_envelope("outbound.reply", {
            "bot_id": bot_id, "channel": channel, "contact_ref": contact_ref,
            "jwe_body": text,   # el servicio de salida cifra/entrega; MVP texto plano
        }, self._cfg.producer))
        self._log.record_action(event_id, "reply", "SENT", "")

    def _publish_report(self, bot_id, channel, contact_ref, event_id, draft: ReportDraft) -> None:
        self._report.publish_report(build_envelope("report.received", {
            "intention": draft.intention,
            "subject_name": draft.subject_name,
            "id_type": draft.id_type,
            "id_number": draft.id_number,
            "notes": draft.notes,
            "source": f"chatbot:{channel}",
            "contact_ref": contact_ref,
        }, self._cfg.producer))
        self._log.record_action(event_id, "report_captured", "OK", draft.intention)
