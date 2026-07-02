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
from ..domain.disambiguation import parse_multi_selection, parse_selection, parse_yes_no
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
# Confirmación determinística que SOLO se añade cuando el reporte se emite de verdad (no la dice el LLM).
_REPORT_REGISTERED = "\n\n📝 Tu reporte quedó registrado; te avisaremos al validarlo."
# Tras varias fotos inservibles seguidas, se deriva a un coordinador humano (ADR-0020 RF-19 / AB-N1).
_COORDINATOR_HANDOFF = ("He intentado registrar la foto varias veces sin éxito. Voy a derivar tu caso "
                        "a un coordinador para que te ayude personalmente. Gracias por tu paciencia.")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _closing_summary(profile, data: Optional[dict] = None) -> str:
    """Resumen verificable del reporte para el cierre tipo imagen (ADR-0020 RF-17). Ausentes → 'no
    especificado'. Prioriza `data` (datos REALES del reporte que llegan en entity.enrolled) sobre el
    perfil de sesión, que puede estar vacío para un reporte derivado o ya reseteado (ADR-0021)."""
    d = data or {}
    pick = lambda field: d.get(field) or getattr(profile, field, None)
    id_type, id_number = pick("id_type"), pick("id_number")
    doc = " ".join(x for x in (id_type, id_number) if x) or _NO_ESPECIFICADO
    return ("Reporte completo. Esto fue lo que registramos:\n\n"
            f"Nombre: {pick('subject_name') or _NO_ESPECIFICADO}\n"
            f"Documento de identidad: {doc}\n"
            f"Dónde fue visto por última vez: {pick('location') or _NO_ESPECIFICADO}\n"
            f"Información adicional: {pick('notes') or _NO_ESPECIFICADO}")
# Feedback sobre la foto cuando el enrolamiento no pudo completarse (ADR-0016).
_PHOTO_FEEDBACK = {
    "no_face": ("No pude reconocer un rostro en la foto. ¿Podrías enviar otra, de frente, "
                "bien iluminada y donde se vea claramente la cara?"),
    "low_quality": ("La foto salió poco nítida. ¿Puedes enviar otra más clara y de frente, por favor?"),
    "no_subject_in_photo": ("Entendido, la persona no estaba en esa foto. ¿Puedes enviarme otra?"),
    "expired": ("Pasó el tiempo para vincular la foto. Envíamela de nuevo, por favor."),
}


# Reporte derivado de otros rostros (ADR-0021 RF-21).
_OTHER_FACES_PROMPT = (
    "En la foto detecté a otras {n} persona(s), que te muestro numeradas. ¿A cuál(es) de ellas también "
    "vas a reportar? Responde con los números (p. ej. «1 y 3»), o escribe «ninguno».")
_OTHER_FACES_NONE = "Entendido. No reportaremos a las demás personas; sus imágenes se descartan."
_CONSENT_PROMPT = (
    "Para reportar a esta persona necesito tu consentimiento para procesar su foto y sus datos "
    "(base legal de protección de datos). Si es un menor de edad, se requiere autorización de su "
    "representante. ¿Confirmas que cuentas con ello? (sí/no)")
_CONSENT_DECLINED = "De acuerdo, descartamos a esa persona. Seguimos con las demás si las hay."
_ASK_NAME = "¿Cuál es el nombre completo de esta persona?"
_ASK_ID_TYPE = "¿Qué tipo de documento tiene? (por ejemplo: cédula, pasaporte)"
_ASK_ID_NUMBER = "¿Cuál es el número de documento?"
_DERIVED_REGISTERED = "📝 Reporte de {name} registrado; te avisaremos al validarlo."
_DERIVED_DONE = "Listo, no quedan más personas por reportar de esa foto. Gracias."


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
                 resolved_pub=None, notification_pub=None, other_faces_pub=None) -> None:
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
        self._other_faces = other_faces_pub  # publica other.faces.resolved (ADR-0021 RF-21)

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

        # --- reporte derivado en curso (ADR-0021): el mensaje avanza la máquina consentimiento+captura ---
        if ctx.profile.derived_flow:
            return self._handle_derived_reply(bot_id, channel, contact_ref, event_id, user_text, ctx)

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

        # --- multi-reporte: si ya se emitió un reporte y el LLM detecta un sujeto NUEVO, se reabre
        # un reporte limpio para este contacto (ADR-0020). Refinar el nombre de uno aún no emitido NO
        # resetea (la condición exige report_emitted). ---
        base = ctx.profile
        if draft is not None and base.report_emitted and base.is_new_subject(draft.subject_name):
            base = base.reset_report()
        profile = _accumulate(base, draft)

        # --- control de reportes sobre TODA la conversación: decidir la emisión ANTES de responder,
        # para que la confirmación "registrado" refleje el resultado real (no la afirme el LLM). ---
        outcome = Outcome.REPLIED
        will_emit = profile.report_complete and not profile.report_emitted
        if will_emit:
            reply_text += _REPORT_REGISTERED

        self._publish_reply(bot_id, channel, contact_ref, event_id, reply_text)

        # --- persistir turnos ---
        self._convos.append_turn(key, Turn.now("user", user_text), self._embed.embed(user_text))
        self._convos.append_turn(key, Turn.now("assistant", reply_text), self._embed.embed(reply_text))

        if will_emit:
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
        ref = p.get("report_id") or p.get("entity_id")   # dedup del cierre POR reporte (no permanente)
        if ref and ref == ctx.profile.last_closed_ref:
            return HandleResult(Outcome.REPLIED)   # idempotente ante redelivery del MISMO reporte (RF-23)
        event_id = envelope.get("event_id", "")
        media_ref = p.get("media_ref")
        summary = _closing_summary(ctx.profile, p)   # datos del evento (reporte real) con fallback al perfil
        if media_ref:   # cierre tipo imagen: la foto del reporte (URL firmada al enviar) + resumen como caption
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                summary, kind="image", media_ref=media_ref,
                                report_id=p.get("report_id"))
        else:           # sin foto referenciable: cierre en TEXTO con el mismo resumen (degradación, RF-17)
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                _REPORT_COMPLETE + "\n\n" + summary)
        self._publish_notification(p.get("entity_id"), channel, contact_ref, "closing", event_id)
        # Resetea el reporte en curso (libera report_emitted para el siguiente) y marca este cierre como
        # ya notificado por su ref → el mismo contacto puede registrar otro reporte (ADR-0020, opción C).
        self._convos.save_profile(key, ctx.profile.reset_report(last_closed_ref=ref))
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

    # --- reporte derivado de otros rostros (ADR-0021 RF-21) ---
    def on_other_faces_requested(self, envelope: dict) -> HandleResult:
        """Consulta al reportante por los otros rostros detectados y abre la máquina de captura."""
        p = envelope.get("payload", {}) or {}
        bot_id, channel, contact_ref = p.get("bot_id", ""), p.get("channel", ""), p.get("contact_ref", "")
        faces = [f for f in (p.get("faces", []) or []) if f.get("crop_ref")]
        if not contact_ref or not faces:
            return HandleResult(Outcome.REPLIED)
        key = conversation_key(bot_id, channel, contact_ref)
        ctx = self._load_context(key, "")
        event_id = envelope.get("event_id", "")
        flow = {
            "disambiguation_id": p.get("disambiguation_id"),
            "origin_report_id": p.get("origin_report_id"),
            "origin_entity_id": p.get("origin_entity_id"),
            "faces": [{"index": f.get("index"), "crop_ref": f.get("crop_ref")} for f in faces],
            "queue": [], "current": None, "step": "select",
        }
        self._publish_reply(bot_id, channel, contact_ref, event_id,
                            _OTHER_FACES_PROMPT.format(n=len(faces)),
                            media_refs=[f["crop_ref"] for f in flow["faces"]],
                            report_id=p.get("origin_report_id"))
        self._publish_notification(p.get("origin_entity_id"), channel, contact_ref, "other_faces", event_id)
        self._convos.save_profile(key, replace(ctx.profile, derived_flow=flow))
        return HandleResult(Outcome.REPLIED)

    def _handle_derived_reply(self, bot_id, channel, contact_ref, event_id, user_text,
                              ctx: ConversationContext) -> HandleResult:
        """Avanza la máquina consentimiento+captura del reporte derivado según `derived_flow.step`."""
        flow = dict(ctx.profile.derived_flow)
        step = flow.get("step")

        if step == "select":
            sel = parse_multi_selection(user_text, len(flow["faces"]))
            if sel.kind == "invalid":
                self._publish_reply(bot_id, channel, contact_ref, event_id,
                                    "No entendí. Dime los números (p. ej. «1 y 2»), o «ninguno».")
                return HandleResult(Outcome.REPLIED)
            if sel.kind == "none":
                self._publish_other_faces_resolved(flow["disambiguation_id"], [])
                self._publish_reply(bot_id, channel, contact_ref, event_id, _OTHER_FACES_NONE)
                self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=None))
                return HandleResult(Outcome.REPLIED)
            confirmed = [flow["faces"][i] for i in sel.indices]        # posición mostrada → rostro
            self._publish_other_faces_resolved(flow["disambiguation_id"],
                                               [f["index"] for f in confirmed])   # índice original
            flow["queue"] = confirmed[1:]
            flow["current"] = _new_derived_current(confirmed[0]["crop_ref"])
            flow["step"] = "consent"
            self._publish_reply(bot_id, channel, contact_ref, event_id, _CONSENT_PROMPT)
            self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=flow))
            return HandleResult(Outcome.REPLIED)

        if step == "consent":
            yn = parse_yes_no(user_text)
            if yn == "invalid":
                self._publish_reply(bot_id, channel, contact_ref, event_id,
                                    "¿Confirmas el consentimiento? Responde «sí» o «no».")
                return HandleResult(Outcome.REPLIED)
            if yn == "no":
                self._publish_reply(bot_id, channel, contact_ref, event_id, _CONSENT_DECLINED)
                return self._advance_or_finish(bot_id, channel, contact_ref, event_id, ctx, flow)
            self._publish_notification(flow.get("origin_entity_id"), channel, contact_ref,
                                       "derived_consent", event_id)
            flow["step"] = "name"
            self._publish_reply(bot_id, channel, contact_ref, event_id, _ASK_NAME)
            self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=flow))
            return HandleResult(Outcome.REPLIED)

        if step in ("name", "id_type", "id_number"):
            field = {"name": "subject_name", "id_type": "id_type", "id_number": "id_number"}[step]
            flow["current"][field] = user_text.strip()
            if step == "name":
                flow["step"] = "id_type"
                self._publish_reply(bot_id, channel, contact_ref, event_id, _ASK_ID_TYPE)
                self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=flow))
                return HandleResult(Outcome.REPLIED)
            if step == "id_type":
                flow["step"] = "id_number"
                self._publish_reply(bot_id, channel, contact_ref, event_id, _ASK_ID_NUMBER)
                self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=flow))
                return HandleResult(Outcome.REPLIED)
            # id_number completo → promueve el recorte a reporte derivado (con procedencia)
            cur = flow["current"]
            self._publish_derived_report(bot_id, channel, contact_ref, event_id, flow, cur)
            self._publish_reply(bot_id, channel, contact_ref, event_id,
                                _DERIVED_REGISTERED.format(name=cur.get("subject_name") or "la persona"))
            return self._advance_or_finish(bot_id, channel, contact_ref, event_id, ctx, flow,
                                           outcome=Outcome.REPLIED_WITH_REPORT)

        # step desconocido → cierra el flujo de forma segura
        self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=None))
        return HandleResult(Outcome.REPLIED)

    def _advance_or_finish(self, bot_id, channel, contact_ref, event_id, ctx, flow,
                           outcome=Outcome.REPLIED) -> HandleResult:
        """Pasa al siguiente rostro de la cola (nuevo consentimiento) o cierra el flujo derivado."""
        queue = flow.get("queue", []) or []
        if queue:
            flow2 = {**flow, "queue": queue[1:],
                     "current": _new_derived_current(queue[0]["crop_ref"]), "step": "consent"}
            self._publish_reply(bot_id, channel, contact_ref, event_id, _CONSENT_PROMPT)
            self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=flow2))
        else:
            self._publish_reply(bot_id, channel, contact_ref, event_id, _DERIVED_DONE)
            self._convos.save_profile(ctx.key, replace(ctx.profile, derived_flow=None))
        return HandleResult(outcome)

    def _publish_other_faces_resolved(self, disambiguation_id, confirmed_indices) -> None:
        if self._other_faces is None:
            return
        self._other_faces.publish_other_faces_resolved(build_envelope(
            "other.faces.resolved",
            {"disambiguation_id": disambiguation_id, "confirmed_indices": list(confirmed_indices)},
            self._cfg.producer))

    def _publish_derived_report(self, bot_id, channel, contact_ref, event_id, flow, current) -> None:
        """Emite report.received del derivado: el recorte guardado es su foto de referencia; la
        procedencia (origin_*) queda en attributes para trazabilidad y merge reversible (ADR-0021 §6)."""
        self._report.publish_report(build_envelope("report.received", {
            "intention": "desaparecido",
            "subject_name": current.get("subject_name"),
            "id_type": current.get("id_type"),
            "id_number": current.get("id_number"),
            "media_ref": current.get("crop_ref"),
            "origin_report_id": flow.get("origin_report_id"),
            "origin_entity_id": flow.get("origin_entity_id"),
            "source": f"chatbot:{channel}:derived",
            "contact_ref": contact_ref, "bot_id": bot_id, "channel": channel,
        }, self._cfg.producer))
        self._log.record_action(event_id, "derived_report_captured", "OK", current.get("subject_name") or "")

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


def _new_derived_current(crop_ref: str) -> dict:
    """Estado de captura de un rostro derivado en curso (ADR-0021)."""
    return {"crop_ref": crop_ref, "subject_name": None, "id_type": None, "id_number": None}


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
