"""API del **plano interno** (FastAPI). Emisión/revocación de concesiones. ADR-0017 §3.

Mesh privado (IRSA/mTLS), **nunca** expuesto a Internet (Service sin Ingress). Lo llaman
`output-service`, `chatbot-gateway` y el back office en el momento de enviar, para TTL mínimo.
Convención: este plano **nunca** sirve bytes de medios (eso es el plano público).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..application.grant_service import GrantService
from ..domain.models import Audience, Purpose


class GrantIn(BaseModel):
    media_ref: str
    content_type: str
    purpose: Purpose
    channel: str = "whatsapp"
    audience: Audience | None = None
    ttl_s: int | None = None
    max_uses: int | None = None


class RevokeByRefIn(BaseModel):
    media_ref: str | None = None
    report_id: str | None = None
    entity_id: str | None = None


def create_internal_app(grants: GrantService) -> FastAPI:
    app = FastAPI(title="Respuesta — Media Gateway (interno)", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/grants", status_code=201)
    def issue(body: GrantIn) -> dict:
        issued = grants.issue(
            media_ref=body.media_ref, content_type=body.content_type, purpose=body.purpose,
            created_by=body.channel, audience=body.audience, ttl_s=body.ttl_s, max_uses=body.max_uses)
        return {"url": issued.url, "token_id": issued.token_id, "expires_at": issued.expires_at}

    @app.delete("/grants/{token_id}", status_code=204)
    def revoke(token_id: str) -> None:
        grants.revoke(token_id)

    @app.post("/grants:revoke-by-ref", status_code=204)
    def revoke_by_ref(body: RevokeByRefIn) -> None:
        if body.media_ref is None and body.report_id is None and body.entity_id is None:
            raise HTTPException(status_code=422, detail="requiere media_ref, report_id o entity_id")
        grants.revoke_by_ref(media_ref=body.media_ref, report_id=body.report_id,
                             entity_id=body.entity_id)

    return app
