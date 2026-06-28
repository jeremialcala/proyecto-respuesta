"""Nombres de los eventos de auditoría del media-gateway (cadena SHA-256, ADR-0007 / design §7).

Cada emisión, revocación y descarga deja un registro en la auditoría encadenada. No son eventos de
broker (ADR-0011); son entradas de la auditoría append-only.
"""
from __future__ import annotations

GRANT_ISSUED = "grant.issued"     # se emitió una concesión (plano interno)
GRANT_REVOKED = "grant.revoked"   # se revocó una concesión (individual o en lote)
MEDIA_SERVED = "media.served"     # se sirvió (o se rechazó) una descarga (plano público)
