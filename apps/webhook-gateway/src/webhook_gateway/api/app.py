"""API HTTP del Webhook Gateway (FastAPI). Único endpoint público que Meta golpea (ADR-0005).

- GET  /webhooks/{network}/{bot_id} → handshake hub.challenge (verificación de suscripción).
- POST /webhooks/{network}/{bot_id} → recibe, valida firma, deduplica, publica crudo y ACK<5s.

Convención: el endpoint NO procesa ni invoca workers; su única salida es publicar a meta.received.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, Response

from ..application.ingest_service import Decision, IngestService


def create_app(service: IngestService) -> FastAPI:
    app = FastAPI(title="Respuesta — Webhook Gateway de Meta", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/webhooks/{network}/{bot_id}")
    def verify(network: str, bot_id: str, request: Request) -> Response:
        q = request.query_params
        challenge = service.verify_subscription(
            bot_id,
            q.get("hub.mode", ""),
            q.get("hub.verify_token", ""),
            q.get("hub.challenge", ""),
        )
        if challenge is None:
            return Response(status_code=403)
        return Response(content=challenge, media_type="text/plain", status_code=200)

    @app.post("/webhooks/{network}/{bot_id}")
    async def receive(network: str, bot_id: str, request: Request) -> Response:
        raw_body = await request.body()
        sig = request.headers.get("X-Hub-Signature-256")
        try:
            import json
            raw_json = json.loads(raw_body or b"{}")
        except ValueError:
            return Response(status_code=400)
        result = service.ingest(bot_id, raw_body, raw_json, sig)
        # ACK rápido (200) salvo fallo de autenticidad (403). Nunca bloquea en procesamiento.
        return Response(status_code=result.http_status)

    return app
