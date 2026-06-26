"""Veredicto de escaneo de medios (ADR-0005, child-safety). Puro (stdlib).

Regla de seguridad: **CSAM tiene prioridad absoluta**. Si el hash coincide con la lista CSAM, el
veredicto es CSAM aunque el antivirus diga limpio → el binario **no** se persiste y se escala. El
malware (sin CSAM) va a **cuarentena**. Solo lo limpio entra a la bóveda.
"""
from __future__ import annotations

import hashlib

from .models import ScanVerdict


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decide_verdict(*, av_clean: bool, csam_hit: bool) -> ScanVerdict:
    """CSAM > MALWARE > CLEAN. El orden de precedencia es una invariante de seguridad."""
    if csam_hit:
        return ScanVerdict.CSAM
    if not av_clean:
        return ScanVerdict.MALWARE
    return ScanVerdict.CLEAN
