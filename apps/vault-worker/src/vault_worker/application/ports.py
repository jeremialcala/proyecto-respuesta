"""Puertos del Worker de Bóveda. Los adaptadores (Graph, scanner, KMS, S3, SQS) los implementan."""
from __future__ import annotations

from typing import Protocol

from ..domain.models import EncryptedObject


class MediaDownloader(Protocol):
    """Descarga el binario desde la Graph API por media_id (no llega por el webhook)."""

    def download(self, media_id: str, bot_id: str) -> bytes: ...


class MalwareScanner(Protocol):
    """Escaneo AV + hashing CSAM. Devuelve (av_clean, csam_hit)."""

    def scan(self, data: bytes) -> tuple[bool, bool]: ...


class EnvelopeCipher(Protocol):
    """Cifrado de sobre: DEK por objeto/sujeto envuelta por KEK (ADR-0008)."""

    def encrypt(self, data: bytes, subject: str) -> EncryptedObject: ...


class MediaStore(Protocol):
    """Persistencia del objeto cifrado. Devuelve el media_ref (puntero)."""

    def put(self, obj: EncryptedObject, *, key: str, metadata: dict, quarantine: bool = False) -> str: ...


class EventPublisher(Protocol):
    """Publica media.stored para el motor de matching (ADR-0012)."""

    def publish(self, envelope: dict) -> None: ...


class EventLog(Protocol):
    """Traza por pasos (EventAction) — auditoría (ADR-0005). No-op en MVP; CSAM siempre se registra."""

    def record_action(self, event_id: str, action: str, status: str, detail: str = "") -> None: ...
