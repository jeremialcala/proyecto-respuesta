"""Caso de uso: ingestar `report.received`, persistir y emitir `report.ingested` (ADR-0007/0011).

Valida el núcleo obligatorio, asigna `report_id` + `entity_id` (entidad provisional; la resolución/
merge la hace el motor de matching), persiste el reporte con esquema dinámico, registra la auditoría
encadenada y publica `report.ingested`. Reportes inválidos se registran y se descartan (no reintentan).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from ..config import CoreConfig
from ..domain.models import PersonState, Report
from ..domain.report import validate_report
from .chained_audit import ChainedAudit
from .events import build_envelope
from .ports import EntityStore, EventPublisher, ReportStore


@dataclass(frozen=True)
class IntakeResult:
    accepted: bool
    report_id: Optional[str] = None
    entity_id: Optional[str] = None


class IntakeService:
    def __init__(self, cfg: CoreConfig, reports: ReportStore, entities: EntityStore,
                 audit: ChainedAudit, publisher: EventPublisher) -> None:
        self._cfg = cfg
        self._reports = reports
        self._entities = entities
        self._audit = audit
        self._pub = publisher

    def handle(self, report_received_envelope: dict) -> IntakeResult:
        p = report_received_envelope.get("payload", {}) or {}
        validation = validate_report(p)
        source = p.get("source", "unknown")
        if not validation.ok:
            self._audit.record(source, "report.rejected", {"missing": list(validation.missing)})
            return IntakeResult(accepted=False)

        report_id = "rep_" + uuid.uuid4().hex[:12]
        entity_id = "ent_" + uuid.uuid4().hex[:12]
        report = Report(
            intention=p.get("intention", "desaparecido"),
            subject_name=p["subject_name"], id_type=p["id_type"], id_number=p["id_number"],
            attributes={k: v for k, v in p.items()
                        if k not in ("intention", "subject_name", "id_type", "id_number", "source")},
        )
        self._entities.create_entity(entity_id, PersonState.DESAPARECIDO
                                     if report.intention != "autoreporte" else PersonState.A_SALVO)
        self._reports.save_report(report_id, entity_id, report)
        self._audit.record(source, "report.created",
                           {"report_id": report_id, "entity_id": entity_id,
                            "intention": report.intention})
        self._pub.publish("report.ingested", build_envelope("report.ingested", {
            "report_id": report_id, "entity_id": entity_id,
            "media_ref": p.get("media_ref"), "source": source,
        }, self._cfg.producer))
        return IntakeResult(accepted=True, report_id=report_id, entity_id=entity_id)
