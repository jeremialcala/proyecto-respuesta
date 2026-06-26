"""Cliente del LLM on-premises (Ollama) — NO autoritativo (ADR-0001). `urllib` (stdlib), GPU RTX 3090.

Pide al modelo una respuesta cordial + extracción estructurada (JSON) del reporte. El system prompt
acota el rol (no decide estados/matches). La extracción es un **borrador**; lo confirma el core-backend.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

from ..domain.models import ReportDraft

_SYSTEM = (
    "Eres el asistente de Respuesta, una plataforma humanitaria para reunir personas tras un "
    "terremoto. Conversa con empatía y SIEMPRE en español. Tu rol es ayudar a reportar o buscar "
    "personas y extraer datos del reporte. NO decides coincidencias ni cambias estados; eso lo hacen "
    "humanos. Responde SOLO con un JSON: {\"reply\": str, \"report\": {\"intention\": "
    "\"desaparecido|encontrado|autoreporte\", \"subject_name\": str|null, \"id_type\": str|null, "
    "\"id_number\": str|null, \"notes\": str|null} | null}."
)


class OllamaLlmClient:
    def __init__(self, base_url: str, model: str) -> None:
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model

    def _call(self, user_text: str) -> dict:
        req_body = json.dumps({
            "model": self._model, "stream": False, "format": "json",
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": user_text}],
        }).encode()
        req = urllib.request.Request(self._url, data=req_body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (host on-prem propio)
            data = json.loads(resp.read())
        return json.loads(data["message"]["content"])

    def converse(self, user_text: str) -> tuple[str, Optional[ReportDraft]]:
        out = self._call(user_text)
        reply = out.get("reply", "")
        rep = out.get("report")
        draft = None
        if isinstance(rep, dict) and rep.get("intention"):
            complete = bool(rep.get("subject_name") and rep.get("id_type") and rep.get("id_number"))
            draft = ReportDraft(
                intention=rep["intention"], subject_name=rep.get("subject_name"),
                id_type=rep.get("id_type"), id_number=rep.get("id_number"),
                notes=rep.get("notes"), complete=complete)
        return reply, draft
