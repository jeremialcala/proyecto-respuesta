"""Caso de uso del Worker de Bóveda (ADR-0005/0008): descarga → escanea → cifra → persiste → publica.

Invariantes de seguridad:
- **CSAM** (child-safety): el binario **NUNCA** se persiste ni se publica `media.stored`; se registra
  un EventAction de alta severidad y se considera manejado (no reentra al loop).
- **Malware**: va a **cuarentena** cifrada (bucket separado); **no** se publica `media.stored` hacia
  matching.
- Solo lo **limpio** se cifra (sobre, DEK por sujeto — ADR-0008), se persiste en la bóveda y emite
  `media.stored` (scan=clean) correlacionado por `event_id`.
- El binario **siempre** se cifra antes de tocar el almacén; el plano nunca se persiste.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import VaultConfig
from ..domain.models import InboundMedia, ScanVerdict
from ..domain.scan import decide_verdict, sha256_hex
from .events import build_envelope
from .ports import EnvelopeCipher, EventLog, EventPublisher, MalwareScanner, MediaDownloader, MediaStore


@dataclass(frozen=True)
class VaultOutcome:
    verdict: ScanVerdict
    media_ref: Optional[str] = None


def _parse_inbound(envelope: dict) -> InboundMedia:
    p = envelope.get("payload", {}) or {}
    return InboundMedia(
        event_id=envelope.get("event_id", ""),
        bot_id=p.get("bot_id", ""),
        contact_ref=p.get("contact_ref", ""),
        message_id=p.get("message_id", ""),
        media_id=p.get("media_id", ""),
        media_type=p.get("media_type", "image"),
        mime_type=p.get("mime_type"),
    )


class VaultService:
    def __init__(self, cfg: VaultConfig, downloader: MediaDownloader, scanner: MalwareScanner,
                 cipher: EnvelopeCipher, store: MediaStore, publisher: EventPublisher,
                 event_log: EventLog) -> None:
        self._cfg = cfg
        self._dl = downloader
        self._scan = scanner
        self._cipher = cipher
        self._store = store
        self._pub = publisher
        self._log = event_log

    def handle(self, inbound_media_envelope: dict) -> VaultOutcome:
        m = _parse_inbound(inbound_media_envelope)
        data = self._dl.download(m.media_id, m.bot_id)

        av_clean, csam_hit = self._scan.scan(data)
        verdict = decide_verdict(av_clean=av_clean, csam_hit=csam_hit)
        digest = sha256_hex(data)

        if verdict is ScanVerdict.CSAM:
            # Child-safety: no se persiste ni se reenvía; se escala (cola/incidente fuera de alcance).
            self._log.record_action(m.event_id, "scan", "CSAM_BLOCKED", f"sha256={digest}")
            return VaultOutcome(verdict)

        # Cifrado de sobre por sujeto ANTES de tocar el almacén (plano nunca se persiste).
        enc = self._cipher.encrypt(data, subject=m.contact_ref)
        meta = {"event_id": m.event_id, "message_id": m.message_id,
                "media_type": m.media_type, "mime_type": m.mime_type or "", "sha256": digest}

        if verdict is ScanVerdict.MALWARE:
            self._store.put(enc, key=f"quarantine/{m.event_id}/{m.media_id}", metadata=meta, quarantine=True)
            self._log.record_action(m.event_id, "scan", "MALWARE_QUARANTINED", f"sha256={digest}")
            return VaultOutcome(verdict)

        media_ref = self._store.put(enc, key=f"media/{m.contact_ref}/{m.media_id}", metadata=meta)
        self._log.record_action(m.event_id, "store", "OK", media_ref)
        self._pub.publish(build_envelope("media.stored", {
            "event_id": m.event_id,
            "media_ref": media_ref,
            "media_type": m.media_type,
            "scan": "clean",
        }, self._cfg.producer, event_id=m.event_id))
        return VaultOutcome(verdict, media_ref=media_ref)
