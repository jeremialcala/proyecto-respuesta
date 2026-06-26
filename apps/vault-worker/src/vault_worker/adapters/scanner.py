"""Escáner AV + CSAM. MVP: placeholder inyectable; en fase 03, ClamAV + lista de hashes CSAM.

Devuelve (av_clean, csam_hit). El MVP marca todo limpio (NO apto para producción): el escaneo real
es obligatorio antes de persistir (child-safety, ADR-0005).
"""
from __future__ import annotations


class PassthroughScanner:
    """Placeholder explícito: NO escanea. Reemplazar por ClamAV + hashing CSAM en fase 03."""

    def scan(self, data: bytes) -> tuple[bool, bool]:
        return (True, False)  # av_clean=True, csam_hit=False
