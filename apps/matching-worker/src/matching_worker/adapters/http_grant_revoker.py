"""Revocación de concesiones del media-gateway al purgar recortes (ADR-0016 §6 / ADR-0017).

`POST {media_gateway_url}/grants:revoke-by-ref` con `{report_id}` (un solo lote) o, si no hay
`report_id`, por cada `media_ref` (crop_ref). **Best-effort**: una revocación que falla se registra y
no aborta el enrolamiento; el TTL corto de la concesión es el respaldo. `urllib` (stdlib).
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

log = logging.getLogger(__name__)


class HttpGrantRevoker:
    def __init__(self, media_gateway_url: str, *, timeout: int = 10, dry_run: bool = False) -> None:
        self._url = f"{media_gateway_url.rstrip('/')}/grants:revoke-by-ref"
        self._timeout = timeout
        self._dry_run = dry_run

    def revoke_grants(self, *, report_id: Optional[str], media_refs: list[str]) -> None:
        if report_id:
            self._post({"report_id": report_id})            # un lote cubre todos los recortes del reporte
        else:
            for ref in media_refs:                          # sin report_id: revoca por cada crop_ref
                self._post({"media_ref": ref})

    def _post(self, body: dict) -> None:
        if self._dry_run:
            log.info("⇢ [dry-run] revoke-by-ref %s", body)
            return
        req = urllib.request.Request(
            self._url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout):  # noqa: S310 (mesh interno)
                return
        except (urllib.error.URLError, OSError) as e:
            # Best-effort: el TTL de la concesión es el respaldo. No abortamos el enrolamiento.
            log.warning("revoke-by-ref falló (%s) para %s; el TTL de la concesión respalda", e, body)