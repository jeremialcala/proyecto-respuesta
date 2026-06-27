"""Caso de uso de la Pasarela de Chatbot (ADR-0001/0002/0015).

Consume `inbound.text`, descifra, **carga el contexto de la conversación** (memoria por contacto),
pasa rieles de **entrada**, conversa con el **LLM on-prem** dándole ese contexto, pasa rieles de
**salida**, acumula el borrador del reporte en el perfil de sesión y publica `outbound.reply` y
—solo cuando el reporte acumulado a lo largo de la conversación queda completo— `report.received`
(una sola vez). El LLM **no es autoritativo**: este servicio nunca emite `state.changed` ni match.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional

from ..config import ChatbotConfig
from ..domain import guardrails
from ..domain.conversation import (ConversationContext, SessionProfile, Turn,
                                   conversation_key)
from ..domain.models import InputCategory, ReportDraft
from .events import build_envelope
from .ports import (BodyCipher, ConversationStore, Embedder, EventLog, LlmClient,
                    ReplyPublisher, ReportPublisher)

_SAFE_BLOCKED = ("Por tu seguridad no puedo procesar ese mensaje. ¿Puedo ayudarte a reportar o "
                 "buscar a una persona?")
_SAFE_FALLBACK = ("Disculpa, tuve un problema procesando tu mensaje. ¿Puedes reformularlo, por favor?")
_CORDIAL_PREFIX = "Entiendo que es un momento difícil. "

# Aviso al reportante cuando la foto quedó enrolada y el reporte está completo (ADR-0016).
_REPORT_COMPLETE = ("✅ ¡Listo! Tu reporte quedó completo y registrado, incluida la foto que enviaste. "
                    "Gracias por la información. Te avisaremos ante cualquier coincidencia.")
# Feedback sobre la foto cuando el enrolamiento no pudo completarse (ADR-0016).
_PHOTO_FEEDBACK = {
    "no_face": ("No pude reconocer un rostro en la foto. ¿Podrías enviar otra, de frente, "
                "bien iluminada y donde se vea claramente la cara?"),
    "low_quality": ("La foto salió poco nítida. ¿Puedes enviar otra más clara y de frente, por favor?"),
    "no_subject_in_photo": ("Entendido, la persona no estaba en esa foto. ¿Puedes enviarme otra?"),
    "expired": ("Pasó el tiempo para vincular la foto. Envíamela de nuevo, por favor."),
}


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
                 reply_pub: ReplyPublisher, report_pub: ReportPublisher, event_log: EventLog,
                 conversations: ConversationStore, embedder: Embedder) -> None:
        self._cfg = cfg
        self._cipher = cipher
        self._llm = llm
        self._reply = reply_pub
        self._report = report_pub
        self._log = event_log
        self._convos = conversations
        self._embed = embedder

    def handle(self, inbound_text_envelope: dict) -> HandleResult:
        p = inbound_text_envelope.get("payload", {}) or {}
        event_id = inbound_text_envelope.get("event_id", "")
        bot_id, channel = p.get("bot_id", ""), p.get("channel", "")
        contact_ref = p.get("contact_ref", "")
        key = conversation_key(bot_id, channel, contact_ref)   # quién nos habla (estable, no reversible)

        body = json.loads(self._cipher.decrypt(p.get("jwe_body", "") or "{}"))
        if body.get("kind") == "location":
            # Ubicación: contexto, no conversación; ack cordial (sin LLM en el MVP). Se anota en memoria.
            ctx = self._load_context(key, "ubicación compartida")
            self._convos.append_turn(key, Turn.now("user", "[ubicación compartida]"),
                                     self._embed.embed("ubicación compartida"))
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                "Recibí tu ubicación, gracias. La sumo al reporte.")
            self._convos.save_profile(key, _bump(ctx.profile))
            return HandleResult(Outcome.REPLIED)

        user_text = body.get("text", "")

        # --- riel de entrada ---
        screen = guardrails.screen_input(user_text)
        if screen.blocked:
            self._log.record_action(event_id, "input_rail", "BLOCKED", screen.reason)
            self._publish_reply(bot_id, channel, contact_ref, event_id, _SAFE_BLOCKED)
            return HandleResult(Outcome.BLOCKED)

        # --- contexto de la conversación (memoria por contacto) ---
        ctx = self._load_context(key, user_text)

        # --- LLM (no autoritativo), con contexto ---
        reply_text, draft = self._llm.converse(user_text, ctx)

        # --- riel de salida ---
        out = guardrails.screen_output(reply_text)
        if not out.ok:
            self._log.record_action(event_id, "output_rail", out.category.value, out.reason)
            self._publish_reply(bot_id, channel, contact_ref, event_id, _SAFE_FALLBACK)
            # Persistimos el turno del usuario aunque rechacemos la salida (no perdemos su mensaje).
            self._convos.append_turn(key, Turn.now("user", user_text), self._embed.embed(user_text))
            self._convos.save_profile(key, _bump(ctx.profile))
            return HandleResult(Outcome.OUTPUT_REJECTED)

        if screen.category is InputCategory.ABUSE:
            reply_text = _CORDIAL_PREFIX + reply_text   # tono cordial ante insultos (ADR-0002)

        self._publish_reply(bot_id, channel, contact_ref, event_id, reply_text)

        # --- persistir turnos y acumular el borrador en el perfil ---
        self._convos.append_turn(key, Turn.now("user", user_text), self._embed.embed(user_text))
        self._convos.append_turn(key, Turn.now("assistant", reply_text), self._embed.embed(reply_text))
        profile = _accumulate(ctx.profile, draft)

        # --- control de reportes sobre TODA la conversación, no sobre un turno ---
        outcome = Outcome.REPLIED
        if profile.report_complete and not profile.report_emitted:
            self._publish_report(bot_id, channel, contact_ref, event_id, profile)
            profile = replace(profile, report_emitted=True)
            outcome = Outcome.REPLIED_WITH_REPORT

        self._convos.save_profile(key, profile)
        return HandleResult(outcome)

    # --- feedback de enrolamiento (ADR-0016): cierra el lazo con el reportante ---
    def on_entity_enrolled(self, envelope: dict) -> HandleResult:
        """La foto se enroló en el motor de match → avisamos al reportante que su reporte está completo."""
        p = envelope.get("payload", {}) or {}
        bot_id, channel, contact_ref = p.get("bot_id", ""), p.get("channel", ""), p.get("contact_ref", "")
        if not contact_ref:
            return HandleResult(Outcome.REPLIED)   # sin identidad del reportante no podemos avisar
        key = conversation_key(bot_id, channel, contact_ref)
        ctx = self._load_context(key, "")
        if ctx.profile.completion_notified:
            return HandleResult(Outcome.REPLIED)   # idempotente: no repetir el aviso
        self._publish_reply(bot_id, channel, contact_ref, envelope.get("event_id", ""), _REPORT_COMPLETE)
        self._convos.save_profile(key, replace(ctx.profile, completion_notified=True))
        return HandleResult(Outcome.REPLIED)

    def on_enrollment_failed(self, envelope: dict) -> HandleResult:
        """El enrolamiento de la foto falló → guiamos al reportante a reenviar una foto utilizable."""
        p = envelope.get("payload", {}) or {}
        bot_id, channel, contact_ref = p.get("bot_id", ""), p.get("channel", ""), p.get("contact_ref", "")
        reason = p.get("reason", "")
        text = _PHOTO_FEEDBACK.get(reason)
        if not contact_ref or text is None:
            return HandleResult(Outcome.REPLIED)   # invalid_selection u otros: sin acción del usuario
        self._publish_reply(bot_id, channel, contact_ref, envelope.get("event_id", ""), text)
        return HandleResult(Outcome.REPLIED)

    # --- contexto ---
    def _load_context(self, key: str, query_text: str) -> ConversationContext:
        q = self._embed.embed(query_text)
        return self._convos.load(key, q, recent_n=self._cfg.recent_turns,
                                 top_k=self._cfg.retrieval_k)

    # --- publicación ---
    def _publish_reply(self, bot_id, channel, contact_ref, event_id, text) -> None:
        self._reply.publish_reply(build_envelope("outbound.reply", {
            "bot_id": bot_id, "channel": channel, "contact_ref": contact_ref,
            "jwe_body": text,   # el servicio de salida cifra/entrega; MVP texto plano
        }, self._cfg.producer))
        self._log.record_action(event_id, "reply", "SENT", "")

    def _publish_report(self, bot_id, channel, contact_ref, event_id, profile: SessionProfile) -> None:
        self._report.publish_report(build_envelope("report.received", {
            "intention": profile.intention,
            "subject_name": profile.subject_name,
            "id_type": profile.id_type,
            "id_number": profile.id_number,
            "notes": profile.notes,
            "source": f"chatbot:{channel}",
            "contact_ref": contact_ref,
            "bot_id": bot_id,        # identidad del reportante: permite avisarle al cerrarse (ADR-0016)
            "channel": channel,
        }, self._cfg.producer))
        self._log.record_action(event_id, "report_captured", "OK", profile.intention or "")


def _bump(profile: SessionProfile) -> SessionProfile:
    """Incrementa el contador de turnos del perfil."""
    return replace(profile, turn_count=profile.turn_count + 1)


def _accumulate(profile: SessionProfile, draft: Optional[ReportDraft]) -> SessionProfile:
    """Funde el borrador del turno actual sobre el perfil acumulado e incrementa el contador."""
    merged = profile
    if draft is not None:
        merged = profile.merged_with(
            intention=draft.intention, subject_name=draft.subject_name,
            id_type=draft.id_type, id_number=draft.id_number, notes=draft.notes)
    return _bump(merged)
