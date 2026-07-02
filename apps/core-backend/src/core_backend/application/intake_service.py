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
from .events import _utc_now_iso, build_envelope
from .ports import (EntityStore, EventPublisher, MediaCorrelationStore, ReplyPublisher,
                    ReportStore)

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
                        reporter: Optional[dict] = None, summary: Optional[dict] = None) -> None: ...
    def get_report(self, contact_ref: str) -> Optional[dict]: return None


class IntakeService:
    def __init__(self, cfg: CoreConfig, reports: ReportStore, entities: EntityStore,
                 audit: ChainedAudit, publisher: EventPublisher,
                 correlation: MediaCorrelationStore | None = None,
                 reply_pub: ReplyPublisher | None = None) -> None:
        self._cfg = cfg
        self._reports = reports
        self._entities = entities
        self._audit = audit
        self._pub = publisher
        self._corr = correlation or _NoopCorrelation()
        self._reply = reply_pub      # acuse al reportante (RF-16); None → sin acuse (tests sin canal)
        self._acked: set[str] = set()  # acuse una vez por FOTO (media_ref), llegue antes o después el reporte

    def _emit_report_ingested(self, report_id: str, entity_id: str, media_ref: Optional[str],
                              source: str, reporter: Optional[dict] = None,
                              subject_name: Optional[str] = None, summary: Optional[dict] = None) -> None:
        payload = {"report_id": report_id, "entity_id": entity_id,
                   "media_ref": media_ref, "source": source}
        # Resumen del reporte (ADR-0020): viaja hasta entity.enrolled para que el cierre tipo imagen se
        # arme con los datos REALES del reporte (no del perfil de sesión, que puede estar vacío para un
        # reporte derivado o reseteado). Campos ausentes se omiten (el chatbot completa con "no especificado").
        s = summary or {}
        for k in ("subject_name", "id_type", "id_number", "location"):
            v = s.get(k)
            if v:
                payload[k] = v
        if reporter:   # identidad del reportante para cerrar el lazo con feedback (ADR-0016)
            payload.update({"bot_id": reporter.get("bot_id", ""),
                            "channel": reporter.get("channel", ""),
                            "contact_ref": reporter.get("contact_ref", "")})
        self._pub.publish("report.ingested", build_envelope("report.ingested", payload, self._cfg.producer))
        if media_ref:   # hay foto → acusa recepción/análisis al reportante (ADR-0020 RF-16)
            self._ack_photo(media_ref, entity_id, reporter, subject_name or s.get("subject_name"))

    def _ack_photo(self, media_ref: Optional[str], entity_id: Optional[str], reporter: Optional[dict],
                   subject_name: Optional[str] = None) -> None:
        """Acuse "recibimos la foto y la estamos analizando" (RF-16). Una vez por foto; sin canal, no-op.

        Se dispara al recibir la foto AUNQUE el reporte aún no esté completo (dedup por `media_ref`), así
        el reportante siempre ve el resultado de la carga (no depende de que el reporte cierre).
        """
        contact_ref = (reporter or {}).get("contact_ref", "")
        if self._reply is None or not contact_ref or not media_ref or media_ref in self._acked:
            return
        self._acked.add(media_ref)
        channel = (reporter or {}).get("channel", "") or "whatsapp"
        who = f"de {subject_name} " if subject_name else ""
        text = f"Recibimos la foto {who}y la estamos analizando. Te avisaremos en cuanto esté lista."
        self._reply.publish_reply(build_envelope("outbound.reply", {
            "bot_id": (reporter or {}).get("bot_id", ""), "channel": channel,
            "contact_ref": contact_ref, "jwe_body": text}, self._cfg.producer))
        self._pub.publish("notification.sent", build_envelope("notification.sent", {
            "entity_id": entity_id, "channel": channel, "contact_ref": contact_ref,
            "purpose": "ack", "sent_at": _utc_now_iso()}, self._cfg.producer))

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
            subject_name=p["subject_name"], id_type=p.get("id_type"), id_number=p.get("id_number"),
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
        summary = {"subject_name": report.subject_name, "id_type": report.id_type,
                   "id_number": report.id_number, "location": report.attributes.get("location")}
        # Correlación foto↔reporte de consumo ÚNICO (ADR-0016): toma una foto ya esperando (y la libera);
        # si no hay, recuerda ESTE reporte (con su resumen) para vincular una foto futura. Así, con
        # múltiples reportes del mismo contacto, cada foto se empareja con un solo reporte.
        media_ref = p.get("media_ref") or self._corr.get_media(contact_ref)
        if not media_ref:
            self._corr.remember_report(contact_ref, report_id, entity_id, reporter, summary=summary)
        self._emit_report_ingested(report_id, entity_id, media_ref, source, reporter,
                                   subject_name=report.subject_name, summary=summary)
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
        # Consumo ÚNICO: toma un reporte en espera (y lo libera). Si lo hay, esta foto lo enrola y NO se
        # recuerda (queda consumida) → una reentrega de media.stored ya no re-dispara el enrolamiento.
        rep = self._corr.get_report(contact_ref)
        if rep:
            reporter = {"bot_id": rep.get("bot_id", ""), "channel": rep.get("channel", ""),
                        "contact_ref": contact_ref}
            self._emit_report_ingested(rep["report_id"], rep["entity_id"], media_ref,
                                       "media.stored", reporter, summary=rep.get("summary"))
            self._audit.record(contact_ref, "media.linked",
                               {"report_id": rep["report_id"], "media_ref": media_ref})
            log.info("media.stored vinculado a rep=%s → report.ingested (enrolamiento)",
                     rep["report_id"])
        else:
            # La foto llegó antes de completar el reporte: recuérdala para vincular el reporte futuro y
            # acusa recibo igual (RF-16). Dedup del acuse por media_ref.
            self._corr.remember_media(contact_ref, media_ref)
            reporter = {"bot_id": p.get("bot_id", ""), "channel": p.get("channel", ""),
                        "contact_ref": contact_ref}
            self._ack_photo(media_ref, None, reporter)
            log.info("media.stored sin reporte aún (contact=%s) → acuse de foto (RF-16)", contact_ref)
