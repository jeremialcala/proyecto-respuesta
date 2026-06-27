"""Caso de uso: ingestar `report.received`, persistir y emitir `report.ingested` (ADR-0007/0011).

Valida el núcleo obligatorio, asigna `report_id` + `entity_id` (entidad provisional; la resolución/
merge la hace el motor de matching), persiste el reporte con esquema dinámico, registra la auditoría
encadenada y publica `report.ingested`. Reportes inválidos se registran y se descartan (no reintentan).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from ..config import CoreConfig
from ..domain.models import PersonState, Report
from ..domain.report import validate_report
from .chained_audit import ChainedAudit
from .events import build_envelope
from .ports import EntityStore, EventPublisher, MediaCorrelationStore, ReportStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntakeResult:
    accepted: bool
    report_id: Optional[str] = None
    entity_id: Optional[str] = None


class _NoopCorrelation:
    """Default sin Redis (tests): no correlaciona; report.ingested usa solo el media_ref del payload."""

    def remember_media(self, contact_ref: str, media_ref: str) -> None: ...
    def get_media(self, contact_ref: str) -> Optional[str]: return None
    def remember_report(self, contact_ref: str, report_id: str, entity_id: str,
                        reporter: Optional[dict] = None) -> None: ...
    def get_report(self, contact_ref: str) -> Optional[dict]: return None


class IntakeService:
    def __init__(self, cfg: CoreConfig, reports: ReportStore, entities: EntityStore,
                 audit: ChainedAudit, publisher: EventPublisher,
                 correlation: MediaCorrelationStore | None = None) -> None:
        self._cfg = cfg
        self._reports = reports
        self._entities = entities
        self._audit = audit
        self._pub = publisher
        self._corr = correlation or _NoopCorrelation()

    def _emit_report_ingested(self, report_id: str, entity_id: str, media_ref: Optional[str],
                              source: str, reporter: Optional[dict] = None) -> None:
        payload = {"report_id": report_id, "entity_id": entity_id,
                   "media_ref": media_ref, "source": source}
        if reporter:   # identidad del reportante para cerrar el lazo con feedback (ADR-0016)
            payload.update({"bot_id": reporter.get("bot_id", ""),
                            "channel": reporter.get("channel", ""),
                            "contact_ref": reporter.get("contact_ref", "")})
        self._pub.publish("report.ingested", build_envelope("report.ingested", payload, self._cfg.producer))

    def handle(self, report_received_envelope: dict) -> IntakeResult:
        p = report_received_envelope.get("payload", {}) or {}
        validation = validate_report(p)
        source = p.get("source", "unknown")
        if not validation.ok:
            self._audit.record(source, "report.rejected", {"missing": list(validation.missing)})
            return IntakeResult(accepted=False)

        report_id = "rep_" + uuid.uuid4().hex[:12]
        entity_id = "ent_" + uuid.uuid4().hex[:12]
        contact_ref = p.get("contact_ref", "")
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

        # Correlación foto↔reporte (ADR-0016): usa el media_ref del payload o el que ya llegó por
        # media.stored para este contacto. Recuerda el reporte (con la identidad del reportante) para
        # vincular una foto que llegue después y poder avisar al usuario al cerrarse.
        reporter = {"bot_id": p.get("bot_id", ""), "channel": p.get("channel", ""),
                    "contact_ref": contact_ref}
        self._corr.remember_report(contact_ref, report_id, entity_id, reporter)
        media_ref = p.get("media_ref") or self._corr.get_media(contact_ref)
        self._emit_report_ingested(report_id, entity_id, media_ref, source, reporter)
        if media_ref:
            log.info("report.ingested rep=%s con media_ref correlacionado", report_id)
        return IntakeResult(accepted=True, report_id=report_id, entity_id=entity_id)

    def on_media_stored(self, media_stored_envelope: dict) -> None:
        """Foto cifrada en la bóveda: si ya hay reporte de este contacto, dispara el enrolamiento."""
        p = media_stored_envelope.get("payload", {}) or {}
        contact_ref = p.get("contact_ref", "")
        media_ref = p.get("media_ref")
        if not contact_ref or not media_ref or p.get("scan", "clean") != "clean":
            return
        self._corr.remember_media(contact_ref, media_ref)
        rep = self._corr.get_report(contact_ref)
        if rep:
            # El reporte ya existía y se ingirió (quizá sin foto) → re-emite con media_ref para enrolar.
            reporter = {"bot_id": rep.get("bot_id", ""), "channel": rep.get("channel", ""),
                        "contact_ref": contact_ref}
            self._emit_report_ingested(rep["report_id"], rep["entity_id"], media_ref,
                                       "media.stored", reporter)
            self._audit.record(contact_ref, "media.linked",
                               {"report_id": rep["report_id"], "media_ref": media_ref})
            log.info("media.stored vinculado a rep=%s → report.ingested (enrolamiento)",
                     rep["report_id"])
