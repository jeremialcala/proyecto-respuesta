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
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from ..config import ChatbotConfig
from ..domain import guardrails
from ..domain.conversation import (ConversationContext, SessionProfile, Turn,
                                   conversation_key)
from ..domain.disambiguation import parse_selection
from ..domain.models import InputCategory, ReportDraft
from .events import build_envelope
from .ports import (BodyCipher, ConversationStore, Embedder, EventLog, LlmClient,
                    ReplyPublisher, ReportPublisher)

_SAFE_BLOCKED = ("Por tu seguridad no puedo procesar ese mensaje. ¿Puedo ayudarte a reportar o "
                 "buscar a una persona?")
_SAFE_FALLBACK = ("Disculpa, tuve un problema procesando tu mensaje. ¿Puedes reformularlo, por favor?")
_CORDIAL_PREFIX = "Entiendo que es un momento difícil. "

# Aviso al reportante cuando la foto quedó enrolada y el reporte está completo (ADR-0016/0020).
_REPORT_COMPLETE = ("✅ ¡Listo! Tu reporte quedó completo y registrado, incluida la foto que enviaste. "
                    "Gracias por la información. Te avisaremos ante cualquier coincidencia.")
_NO_ESPECIFICADO = "no especificado"
# Tras varias fotos inservibles seguidas, se deriva a un coordinador humano (ADR-0020 RF-19 / AB-N1).
_COORDINATOR_HANDOFF = ("He intentado registrar la foto varias veces sin éxito. Voy a derivar tu caso "
                        "a un coordinador para que te ayude personalmente. Gracias por tu paciencia.")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _closing_summary(profile) -> str:
    """Resumen verificable del reporte para el cierre tipo imagen (ADR-0020 RF-17). Ausentes → 'no especificado'."""
    doc = " ".join(x for x in (profile.id_type, profile.id_number) if x) or _NO_ESPECIFICADO
    return ("Reporte completo. Esto fue lo que registramos:\n\n"
            f"Nombre: {profile.subject_name or _NO_ESPECIFICADO}\n"
            f"Documento de identidad: {doc}\n"
            f"Dónde fue visto por última vez: {profile.location or _NO_ESPECIFICADO}\n"
            f"Información adicional: {profile.notes or _NO_ESPECIFICADO}")
# Feedback sobre la foto cuando el enrolamiento no pudo completarse (ADR-0016).
_PHOTO_FEEDBACK = {
    "no_face": ("No pude reconocer un rostro en la foto. ¿Podrías enviar otra, de frente, "
                "bien iluminada y donde se vea claramente la cara?"),
    "low_quality": ("La foto salió poco nítida. ¿Puedes enviar otra más clara y de frente, por favor?"),
    "no_subject_in_photo": ("Entendido, la persona no estaba en esa foto. ¿Puedes enviarme otra?"),
    "expired": ("Pasó el tiempo para vincular la foto. Envíamela de nuevo, por favor."),
}


def _disambiguation_prompt(n: int) -> str:
    return (f"Detecté {n} rostros en la foto que enviaste. Te los muestro numerados. ¿Cuál es la "
            f"persona del reporte? Responde con el número (del 1 al {n}), o escribe «ninguno» si no "
            f"aparece.")


def _disambiguation_retry(n: int) -> str:
    return f"No entendí. Responde con un número del 1 al {n}, o escribe «ninguno»."


class Outcome(Enum):
    REPLIED = "replied"
    REPLIED_WITH_REPORT = "replied_with_report"
    BLOCKED = "blocked"
    OUTPUT_REJECTED = "output_rejected"
    DISAMBIGUATION_PROMPTED = "disambiguation_prompted"   # se mostraron los rostros al reportante
    DISAMBIGUATION_RESOLVED = "disambiguation_resolved"   # el reportante eligió (o descartó)


@dataclass(frozen=True)
class HandleResult:
    outcome: Outcome


class ChatbotService:
    def __init__(self, cfg: ChatbotConfig, cipher: BodyCipher, llm: LlmClient,
                 reply_pub: ReplyPublisher, report_pub: ReportPublisher, event_log: EventLog,
                 conversations: ConversationStore, embedder: Embedder,
                 resolved_pub=None, notification_pub=None) -> None:
        self._cfg = cfg
        self._cipher = cipher
        self._llm = llm
        self._reply = reply_pub
        self._report = report_pub
        self._log = event_log
        self._convos = conversations
        self._embed = embedder
        self._resolved = resolved_pub   # publica face.disambiguation.resolved (ADR-0016)
        self._notify = notification_pub  # publica notification.sent (auditoría, ADR-0020 RF-22)

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

        # --- contexto de la conversación (memoria por contacto) ---
        ctx = self._load_context(key, user_text)

        # --- desambiguación pendiente: el mensaje es la elección del rostro, no conversación ---
        if ctx.profile.pending_disambiguation_id:
            return self._handle_disambiguation_reply(bot_id, channel, contact_ref, event_id,
                                                     user_text, ctx)

        # --- riel de entrada ---
        screen = guardrails.screen_input(user_text)
        if screen.blocked:
            self._log.record_action(event_id, "input_rail", "BLOCKED", screen.reason)
            self._publish_reply(bot_id, channel, contact_ref, event_id, _SAFE_BLOCKED)
            return HandleResult(Outcome.BLOCKED)

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
        """Cierre del reporte (ADR-0020 RF-17/18): mensaje de tipo imagen (foto + resumen) al reportante."""
        p = envelope.get("payload", {}) or {}
        bot_id, channel, contact_ref = p.get("bot_id", ""), p.get("channel", ""), p.get("contact_ref", "")
        if not contact_ref:
            return HandleResult(Outcome.REPLIED)   # sin identidad del reportante no podemos avisar
        key = conversation_key(bot_id, channel, contact_ref)
        ctx = self._load_context(key, "")
        if ctx.profile.completion_notified:
            return HandleResult(Outcome.REPLIED)   # idempotente: una sola notificación de cierre (RF-23)
        event_id = envelope.get("event_id", "")
        media_ref = p.get("media_ref")
        if media_ref:   # cierre tipo imagen: la foto del reporte (URL firmada al enviar) + resumen como caption
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                _closing_summary(ctx.profile), kind="image", media_ref=media_ref,
                                report_id=p.get("report_id"))
        else:           # sin foto referenciable: cierre en texto (degradación)
            self._publish_reply(bot_id, channel, contact_ref, event_id, _REPORT_COMPLETE)
        self._publish_notification(p.get("entity_id"), channel, contact_ref, "closing", event_id)
        self._convos.save_profile(key, replace(ctx.profile, completion_notified=True))
        return HandleResult(Outcome.REPLIED)

    def on_enrollment_failed(self, envelope: dict) -> HandleResult:
        """Foto inservible → pide mejor foto; tras el límite de reintentos deriva a coordinador (RF-19)."""
        p = envelope.get("payload", {}) or {}
        bot_id, channel, contact_ref = p.get("bot_id", ""), p.get("channel", ""), p.get("contact_ref", "")
        reason = p.get("reason", "")
        text = _PHOTO_FEEDBACK.get(reason)
        if not contact_ref or text is None:
            return HandleResult(Outcome.REPLIED)   # invalid_selection u otros: sin acción del usuario
        event_id = envelope.get("event_id", "")
        if reason in ("no_face", "low_quality"):   # cuenta los reintentos de foto utilizable (AB-N1)
            key = conversation_key(bot_id, channel, contact_ref)
            ctx = self._load_context(key, "")
            retries = ctx.profile.photo_retry_count + 1
            if retries > self._cfg.max_photo_retries:
                text = _COORDINATOR_HANDOFF
            self._convos.save_profile(key, replace(ctx.profile, photo_retry_count=retries))
        self._publish_reply(bot_id, channel, contact_ref, event_id, text)
        self._publish_notification(p.get("entity_id"), channel, contact_ref, "better_photo", event_id)
        return HandleResult(Outcome.REPLIED)

    # --- desambiguación multi-rostro (ADR-0016): pregunta al reportante cuál rostro es ---
    def on_face_disambiguation_requested(self, envelope: dict) -> HandleResult:
        """≥2 rostros en la foto: muestra las miniaturas numeradas y queda a la espera de la elección."""
        p = envelope.get("payload", {}) or {}
        bot_id, channel, contact_ref = p.get("bot_id", ""), p.get("channel", ""), p.get("contact_ref", "")
        disambiguation_id = p.get("disambiguation_id")
        faces = p.get("faces", []) or []
        if not contact_ref or not disambiguation_id or len(faces) < 2:
            return HandleResult(Outcome.REPLIED)   # sin con qué preguntar
        key = conversation_key(bot_id, channel, contact_ref)
        ctx = self._load_context(key, "")
        crop_refs = [f.get("crop_ref") for f in faces if f.get("crop_ref")]
        self._publish_reply(bot_id, channel, contact_ref, envelope.get("event_id", ""),
                            _disambiguation_prompt(len(faces)), media_refs=crop_refs,
                            report_id=p.get("report_id"))
        self._publish_notification(p.get("entity_id"), channel, contact_ref, "disambiguation",
                                   envelope.get("event_id", ""))
        self._convos.save_profile(key, replace(
            ctx.profile, pending_disambiguation_id=disambiguation_id, pending_faces_count=len(faces)))
        return HandleResult(Outcome.DISAMBIGUATION_PROMPTED)

    def _handle_disambiguation_reply(self, bot_id, channel, contact_ref, event_id, user_text,
                                     ctx: ConversationContext) -> HandleResult:
        """Interpreta la respuesta del reportante a una desambiguación pendiente y la resuelve."""
        profile = ctx.profile
        sel = parse_selection(user_text, profile.pending_faces_count)
        if sel.kind == "invalid":
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                _disambiguation_retry(profile.pending_faces_count))
            return HandleResult(Outcome.DISAMBIGUATION_PROMPTED)   # sigue pendiente
        if sel.kind == "none":
            self._publish_resolved(profile.pending_disambiguation_id, none=True)
            ack = "Entendido, ninguno era la persona. Te pediré otra foto si hace falta."
        else:
            self._publish_resolved(profile.pending_disambiguation_id, index=sel.index)
            ack = f"¡Gracias! Tomé el rostro #{sel.index + 1} para el reporte."
        self._publish_reply(bot_id, channel, contact_ref, event_id, ack)
        self._convos.save_profile(ctx.key, replace(
            profile, pending_disambiguation_id=None, pending_faces_count=0))
        return HandleResult(Outcome.DISAMBIGUATION_RESOLVED)

    # --- contexto ---
    def _load_context(self, key: str, query_text: str) -> ConversationContext:
        q = self._embed.embed(query_text)
        return self._convos.load(key, q, recent_n=self._cfg.recent_turns,
                                 top_k=self._cfg.retrieval_k)

    # --- publicación ---
    def _publish_reply(self, bot_id, channel, contact_ref, event_id, text, media_refs=None,
                       report_id=None, kind="text", media_ref=None) -> None:
        payload = {
            "bot_id": bot_id, "channel": channel, "contact_ref": contact_ref,
            "jwe_body": text,   # el servicio de salida cifra/entrega; MVP texto plano (o caption si imagen)
        }
        if media_refs:   # miniaturas a mostrar (desambiguación, ADR-0016); el servicio de salida las envía
            payload["media_refs"] = media_refs
        if report_id:    # etiqueta las concesiones del media-gateway para revocarlas al purgar (§6)
            payload["report_id"] = report_id
        if kind == "image":   # cierre tipo imagen (ADR-0020): una foto + caption (URL firmada al enviar)
            payload["kind"] = "image"
            if media_ref:
                payload["media"] = {"media_ref": media_ref}
        self._reply.publish_reply(build_envelope("outbound.reply", payload, self._cfg.producer))
        self._log.record_action(event_id, "reply", "SENT", "")

    def _publish_notification(self, entity_id, channel, contact_ref, purpose, event_id) -> None:
        """Audita la notificación emitida al reportante (ADR-0020 RF-22). No-op si no hay publisher."""
        if self._notify is None:
            return
        payload = {"entity_id": entity_id, "channel": channel, "contact_ref": contact_ref,
                   "purpose": purpose, "sent_at": _utc_now_iso()}
        self._notify.publish_notification(
            build_envelope("notification.sent", payload, self._cfg.producer))
        self._log.record_action(event_id, "notification", purpose, "")

    def _publish_resolved(self, disambiguation_id, *, index=None, none=False) -> None:
        payload = {"disambiguation_id": disambiguation_id}
        if none:
            payload["action"] = "none_of_these"
        else:
            payload["selected_index"] = index
        self._resolved.publish_resolved(
            build_envelope("face.disambiguation.resolved", payload, self._cfg.producer))

    def _publish_report(self, bot_id, channel, contact_ref, event_id, profile: SessionProfile) -> None:
        self._report.publish_report(build_envelope("report.received", {
            "intention": profile.intention,
            "subject_name": profile.subject_name,
            "id_type": profile.id_type,
            "id_number": profile.id_number,
            "location": profile.location,
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
            id_type=draft.id_type, id_number=draft.id_number, notes=draft.notes,
            location=draft.location)
    return _bump(merged)
