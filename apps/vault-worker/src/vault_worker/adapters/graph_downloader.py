"""Descarga del binario desde la Graph API por media_id (ADR-0005). `urllib` (stdlib), token perezoso.

Dos pasos de Meta: GET /{media_id} → URL temporal; GET URL → binario. El token del bot se lee del
secrets manager (Vault) — aquí se inyecta por entorno/parametro. El binario nunca pasó por el webhook.
"""
from __future__ import annotations

import json
import os
import urllib.request


class GraphMediaDownloader:
    def __init__(self, api_base: str, token_provider=None) -> None:
        self._base = api_base.rstrip("/")
        # token_provider(bot_id) -> str; por defecto lee de entorno (MVP).
        self._token_provider = token_provider or (lambda bot_id: os.getenv("META_GRAPH_TOKEN", ""))

    def _get(self, url: str, token: str) -> bytes:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (URL de Meta, no de usuario)
            return resp.read()

    def download(self, media_id: str, bot_id: str) -> bytes:
        token = self._token_provider(bot_id)
        meta = json.loads(self._get(f"{self._base}/{media_id}", token))
        media_url = meta["url"]
        return self._get(media_url, token)
