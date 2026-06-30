"""Cliente del LLM on-premises (Ollama) — NO autoritativo (ADR-0001). `urllib` (stdlib), GPU RTX 3090.

Pide al modelo una respuesta cordial + extracción estructurada (JSON) del reporte. El system prompt
acota el rol (no decide estados/matches). La extracción es un **borrador**; lo confirma el core-backend.

Multi-turno (ADR-0015): construye los `messages` desde el `ConversationContext` —resumen del perfil
acumulado en el system, turnos recuperados por similitud como contexto, ventana reciente como
historial y, por último, el mensaje actual. Así el modelo recuerda lo ya dicho sin reenviar todo.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Optional

from ..domain.conversation import ConversationContext
from ..domain.models import ReportDraft

log = logging.getLogger(__name__)

_SYSTEM = (
    "Eres el asistente de Respuesta, una plataforma humanitaria para reunir personas tras un "
    "terremoto. Conversa con empatía y SIEMPRE en español. Tu rol es ayudar a reportar o buscar "
    "personas y extraer datos del reporte. El usuario SÍ puede enviarte una FOTO de la persona "
    "(desaparecida o encontrada): es muy útil para el reporte, así que pídela con tacto e indícale "
    "que la mande por este mismo chat. NUNCA digas que no puedes recibir imágenes; el sistema las "
    "procesa de forma segura. Recuerdas lo que la persona ya te dijo en esta "
    "conversación: NO vuelvas a pedir datos que ya tienes. NO decides coincidencias ni cambias "
    "estados; eso lo hacen humanos. NO tienes acceso a una base de datos ni a un registro de reportes: "
    "NUNCA inventes reportes previos, ni afirmes 'según mi registro', ni digas que muestras un reporte "
    "guardado. Si te preguntan a quién han reportado o que muestres 'el reporte', responde SOLO con lo "
    "capturado en ESTA conversación (lo que aparece en 'Datos ya conocidos'); si aún no hay datos, dilo "
    "con claridad y pide la información que falta. Lo ESENCIAL para registrar un reporte es: el NOMBRE de "
    "la persona y DÓNDE fue vista por última vez (y, si puede, una FOTO). El documento de identidad "
    "(cédula) es OPCIONAL: pídelo UNA sola vez con tacto, pero si no lo tienen, NO insistas ni bloquees "
    "el reporte por eso —mucha gente reporta a un familiar sin tener su cédula a mano. "
    "NUNCA afirmes que registraste, guardaste o creaste el reporte (no digas 'ya registré', 'quedó "
    "guardado', etc.): el sistema confirma el registro por separado. Limítate a acusar recibo con "
    "empatía y a pedir lo que falte. "
    "Responde SOLO con un JSON: {\"reply\": str, \"report\": "
    "{\"intention\": \"desaparecido|encontrado|autoreporte\", \"subject_name\": str|null, "
    "\"id_type\": str|null, \"id_number\": str|null, \"location\": str|null, \"notes\": str|null} | null}. "
    "\"location\" es DÓNDE fue vista por última vez la persona. Si el mensaje menciona CUALQUIER lugar "
    "(dirección, urbanización, barrio, ciudad, estado o punto de referencia) donde se la vio, DEBES "
    "ponerlo en \"location\" —nunca lo dejes en null ni lo metas solo en \"notes\" si hay un lugar. "
    "Si la persona reporta a alguien DISTINTO al del reporte anterior, empieza un \"report\" nuevo con "
    "los datos del nuevo sujeto."
)


class OllamaLlmClient:
    def __init__(self, base_url: str, model: str, timeout: int = 120,
                 keep_alive: str = "30m") -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._timeout = timeout
        self._keep_alive = keep_alive

    def _build_messages(self, user_text: str, context: ConversationContext) -> list[dict]:
        system = _SYSTEM
        summary = context.profile_summary()
        if summary:
            system += f"\n\nDatos ya conocidos de esta conversación: {summary}."
        messages = [{"role": "system", "content": system}]

        # Turnos antiguos relevantes (recuperados por similitud) como contexto adicional.
        if context.retrieved:
            recordatorio = " | ".join(f"{t.role}: {t.text}" for t in context.retrieved)
            messages.append({"role": "system",
                             "content": f"Fragmentos relevantes anteriores: {recordatorio}"})

        # Ventana reciente como historial real de la conversación.
        for t in context.recent:
            role = "assistant" if t.role == "assistant" else "user"
            messages.append({"role": role, "content": t.text})

        messages.append({"role": "user", "content": user_text})
        return messages

    def _call(self, user_text: str, context: ConversationContext) -> dict:
        req_body = json.dumps({
            "model": self._model, "stream": False, "format": "json",
            "keep_alive": self._keep_alive,   # mantiene el modelo en VRAM (evita recargas por mensaje)
            "messages": self._build_messages(user_text, context),
        }).encode()
        req = urllib.request.Request(self._url, data=req_body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 (host on-prem propio)
                data = json.loads(resp.read())
        except TimeoutError:
            log.error("Ollama timeout (%ss) modelo=%s en %s — ¿modelo no cargado o cola saturada?",
                      self._timeout, self._model, self._url)
            raise
        return json.loads(data["message"]["content"])

    def converse(self, user_text: str, context: ConversationContext
                 ) -> tuple[str, Optional[ReportDraft]]:
        out = self._call(user_text, context)
        reply = out.get("reply", "")
        rep = out.get("report")
        draft = None
        if isinstance(rep, dict) and rep.get("intention"):
            # Accionable = nombre + una pista localizable (ubicación); el documento es opcional.
            complete = bool(rep.get("subject_name") and rep.get("location"))
            draft = ReportDraft(
                intention=rep["intention"], subject_name=rep.get("subject_name"),
                id_type=rep.get("id_type"), id_number=rep.get("id_number"),
                notes=rep.get("notes"), location=rep.get("location"), complete=complete)
        return reply, draft
