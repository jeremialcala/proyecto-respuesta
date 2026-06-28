"""API del **plano público** (FastAPI). Único endpoint que Meta golpea (tras ALB+WAF). ADR-0017 §3.

`GET/HEAD /m/{token}` entrega los bytes descifrados de un medio bajo concesión verificada, fail-closed.
No expone listado ni metadatos; `404` es indistinguible entre token inexistente y HMAC inválido
(anti-enumeración). Convención: este plano **nunca** emite ni revoca concesiones (eso es el interno).
"""
from __future__ import annotations

from fastapi import FastAPI, Request, Response

from ..application.delivery_service import DeliveryService
from ..domain.models import ServeResult

_STATUS = {
    ServeResult.FORBIDDEN: 403,
    ServeResult.NOT_FOUND: 404,
    ServeResult.GONE: 410,
    ServeResult.RATE_LIMITED: 429,
}


def _client_ip(request: Request) -> str:
    # Tras ALB el origen real va en X-Forwarded-For (primer salto). Sin él, el peer directo.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def create_public_app(delivery: DeliveryService) -> FastAPI:
    app = FastAPI(title="Respuesta — Media Gateway (público)", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.api_route("/m/{token}", methods=["GET", "HEAD"])
    def serve(token: str, request: Request) -> Response:
        outcome = delivery.serve(
            token,
            src_ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
        if outcome.result is not ServeResult.OK:
            return Response(status_code=_STATUS[outcome.result])
        headers = {
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
        }
        # HEAD: Meta a veces lo hace antes del GET → mismas cabeceras, sin cuerpo.
        body = b"" if request.method == "HEAD" else (outcome.body or b"")
        return Response(content=body, media_type=outcome.content_type, headers=headers,
                        status_code=200)

    return app
