"""Cliente del plano interno del media-gateway: emite una concesión y devuelve la URL firmada.

`POST {media_gateway_url}/grants` → `{url, token_id, expires_at}` (ADR-0017 §3). Se llama en el
momento del envío para que el TTL de la URL sea mínimo. `urllib` (stdlib), como el GraphSender.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class HttpMediaGrantClient:
    def __init__(self, media_gateway_url: str, *, timeout: int = 10, dry_run: bool = False) -> None:
        self._base = media_gateway_url.rstrip("/")
        self._timeout = timeout
        self._dry_run = dry_run

    def issue_grant(self, media_ref: str, *, content_type: str, purpose: str, channel: str,
                    report_id: str | None) -> str:
        body = {"media_ref": media_ref, "content_type": content_type, "purpose": purpose,
                "channel": channel, "report_id": report_id}
        if self._dry_run:
            # Dev local sin media-gateway: URL ficticia trazable (no se llama a la red).
            log.info("⇢ [dry-run] grant media_ref=%s purpose=%s → URL ficticia", media_ref, purpose)
            return f"{self._base}/m/dry-run-token"
        url = f"{self._base}/grants"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 (mesh interno)
                return json.loads(resp.read())["url"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            log.error("media-gateway %s en %s → %s", e.code, url, detail)
            raise
