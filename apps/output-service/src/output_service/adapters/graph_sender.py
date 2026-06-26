"""Envío por la Graph API de Meta (texto o plantilla HSM) — ADR componente 1. `urllib` (stdlib).

Token del bot desde secrets (Vault). MVP: WhatsApp Cloud API (`/{phone_number_id}/messages`).
"""
from __future__ import annotations

import json
import os
import urllib.request


class GraphSender:
    def __init__(self, api_base: str, token_provider=None, phone_id_provider=None) -> None:
        self._base = api_base.rstrip("/")
        self._token = token_provider or (lambda bot_id: os.getenv("META_GRAPH_TOKEN", ""))
        self._phone = phone_id_provider or (lambda bot_id: os.getenv("WA_PHONE_NUMBER_ID", ""))

    def _post(self, bot_id: str, body: dict) -> None:
        url = f"{self._base}/{self._phone(bot_id)}/messages"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self._token(bot_id)}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30):  # noqa: S310 (endpoint de Meta)
            return None

    def send_text(self, bot_id, channel, contact_ref, text) -> None:
        self._post(bot_id, {"messaging_product": "whatsapp", "to": contact_ref,
                            "type": "text", "text": {"body": text}})

    def send_template(self, bot_id, channel, contact_ref, template, lang) -> None:
        self._post(bot_id, {"messaging_product": "whatsapp", "to": contact_ref,
                            "type": "template",
                            "template": {"name": template, "language": {"code": lang}}})
