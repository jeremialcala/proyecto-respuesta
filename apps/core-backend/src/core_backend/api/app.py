"""API REST del Core Backend (FastAPI). Endpoints del flujo central (openapi.yaml).

MVP: crear reporte y transición de estado, con la misma lógica de dominio que el worker. Auth (RS-01)
y rate-limit se añaden por el edge/ALB y Auth0 (ADR-0009) en fase 03.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..application.intake_service import IntakeService
from ..application.state_service import StateService, TransitionError
from ..domain.models import Mechanism, PersonState


class ReportIn(BaseModel):
    intention: str = "desaparecido"
    subject_name: str
    id_type: str
    id_number: str
    source: str = "portal"
    attributes: dict = {}


class StateIn(BaseModel):
    to_state: str
    mechanism: str
    actor: str
    evidence_ref: str | None = None


def create_app(intake: IntakeService, state: StateService) -> FastAPI:
    app = FastAPI(title="Respuesta — Core Backend", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/reports", status_code=201)
    def create_report(body: ReportIn) -> dict:
        env = {"event_id": "api", "payload": {**body.model_dump(), **body.attributes}}
        res = intake.handle(env)
        if not res.accepted:
            raise HTTPException(status_code=422, detail="reporte incompleto (núcleo obligatorio)")
        return {"report_id": res.report_id, "entity_id": res.entity_id}

    @app.post("/entities/{entity_id}/state")
    def transition(entity_id: str, body: StateIn) -> dict:
        try:
            res = state.transition(entity_id, PersonState(body.to_state),
                                   Mechanism(body.mechanism), body.actor, body.evidence_ref)
        except TransitionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError:
            raise HTTPException(status_code=422, detail="estado o mecanismo inválido")
        return {"entity_id": res.entity_id, "state": res.to_state.value}

    return app


def build_default_app():
    """App por defecto para uvicorn (`core_backend.api.app:app`). Wiring desde entorno."""
    from ..config import CoreConfig
    from ..adapters.pg_stores import PgStores
    from ..adapters.sns_publisher import SnsPublisher
    from ..adapters.sqs_reply_publisher import SqsReplyPublisher
    from ..application.chained_audit import ChainedAudit
    cfg = CoreConfig.from_env()
    stores = PgStores(cfg.pgvector_dsn)
    pub = SnsPublisher({"report.ingested": cfg.report_ingested_topic_arn,
                        "state.changed": cfg.state_changed_topic_arn,
                        "notification.sent": cfg.notification_sent_topic_arn}, cfg.aws_region)
    reply_pub = SqsReplyPublisher(cfg.outbound_reply_queue_url, cfg.aws_region)  # acuse RF-16
    audit = ChainedAudit(stores)
    return create_app(IntakeService(cfg, stores, stores, audit, pub, reply_pub=reply_pub),
                      StateService(cfg, stores, audit, pub))


app = build_default_app()
