"""Modelos de dominio del Worker de Bóveda."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ScanVerdict(Enum):
    CLEAN = "clean"           # apto para persistir en la bóveda
    MALWARE = "malware"       # va a cuarentena, no a la bóveda normal
    CSAM = "csam"             # child-safety: NO se persiste; se escala y bloquea


@dataclass(frozen=True)
class InboundMedia:
    """Referencia a un adjunto entrante (lo emite el Meta Handler en inbound.media)."""
    event_id: str
    bot_id: str
    contact_ref: str          # sujeto → clave por usuario (DEK por sujeto, ADR-0008)
    message_id: str
    media_id: str             # id de la Graph API para descargar el binario
    media_type: str           # image (MVP)
    mime_type: Optional[str] = None


@dataclass(frozen=True)
class ScanReport:
    verdict: ScanVerdict
    sha256: str               # hash del binario (trazabilidad/auditoría)


@dataclass(frozen=True)
class EncryptedObject:
    """Resultado del cifrado de sobre (DEK por objeto envuelta por KEK — ADR-0008)."""
    ciphertext: bytes
    wrapped_dek: bytes
    key_id: str
    subject: str              # contact_ref dueño de la clave


@dataclass(frozen=True)
class StoredMedia:
    media_ref: str            # puntero al objeto cifrado en la bóveda (S3)
    scan: str                 # clean | quarantined
