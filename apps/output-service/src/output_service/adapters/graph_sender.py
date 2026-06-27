"""Envío por la Graph API de Meta (texto o plantilla HSM) — ADR componente 1. `urllib` (stdlib).

Token del bot desde secrets (Vault). MVP: WhatsApp Cloud API (`/{phone_number_id}/messages`).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class GraphSender:
    def __init__(self, api_base: str, token_provider=None, phone_id_provider=None,
                 dry_run: bool = False) -> None:
        self._base = api_base.rstrip("/")
        self._token = token_provider or (lambda bot_id: os.getenv("META_GRAPH_TOKEN", ""))
        self._phone = phone_id_provider or (lambda bot_id: os.getenv("WA_PHONE_NUMBER_ID", ""))
        self._dry_run = dry_run

    def _post(self, bot_id: str, body: dict) -> None:
        url = f"{self._base}/{self._phone(bot_id)}/messages"
        if self._dry_run:
            # Dev local: sin credenciales reales de Meta. Loguea el envío en vez de llamar a la Graph API.
            log.info("⇢ [dry-run] envío a Meta bot_id=%s → %s body=%s",
                     bot_id, url, json.dumps(body, ensure_ascii=False))
            return None
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._token(bot_id)}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30):  # noqa: S310 (endpoint de Meta)
                return None
        except urllib.error.HTTPError as e:
            # Meta devuelve un JSON con el detalle del error (code/subcode/message); súbelo al log.
            detail = e.read().decode("utf-8", "replace")
            log.error("Graph API %s en %s → %s", e.code, url, detail)
            raise

    def send_text(self, bot_id, channel, contact_ref, text) -> None:
        self._post(bot_id, {"messaging_product": "whatsapp", "to": contact_ref,
                            "type": "text", "text": {"body": text}})

    def send_template(self, bot_id, channel, contact_ref, template, lang) -> None:
        self._post(bot_id, {"messaging_product": "whatsapp", "to": contact_ref,
                            "type": "template",
                            "template": {"name": template, "language": {"code": lang}}})
