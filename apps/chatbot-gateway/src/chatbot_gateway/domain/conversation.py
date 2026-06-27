"""Contexto de conversación del chatbot (memoria por contacto).

El chatbot es **multi-turno**: el control de reportes necesita el contexto de *toda* la
conversación con un mismo interlocutor, no de un mensaje suelto. Este módulo define la identidad
estable del interlocutor (`conversation_key`), el historial de turnos y el **perfil de sesión** —el
borrador del reporte que se va completando a lo largo de varios mensajes.

Decisiones de privacidad (ADR-0006/0007/0008/0015):
- La clave de conversación es un **hash** de (bot_id, channel, contact_ref); el handle crudo del
  contacto (teléfono/PSID) no se usa como clave ni se persiste en claro aquí.
- El perfil guarda solo lo que el contacto declara en la conversación; no resuelve identidad
  verificada (eso es ADR-0009, fuera de alcance de esta capa).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional


def conversation_key(bot_id: str, channel: str, contact_ref: str) -> str:
    """Identidad estable y no reversible del interlocutor (quién nos habla).

    Determinística para que los turnos de un mismo contacto caigan en la misma sesión, pero sin
    exponer el handle crudo (teléfono/PSID) como clave primaria.
    """
    raw = f"{bot_id or ''}|{channel or ''}|{contact_ref or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Turn:
    """Un turno de la conversación. `role` es 'user' o 'assistant'."""
    role: str
    text: str
    ts: str = ""

    @staticmethod
    def now(role: str, text: str) -> "Turn":
        return Turn(role=role, text=text,
                    ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


# Campos del núcleo obligatorio de un reporte (igual que ReportDraft).
_CORE_FIELDS = ("subject_name", "id_type", "id_number")


@dataclass(frozen=True)
class SessionProfile:
    """Datos acumulados de ESTA conversación: lo que sabemos del interlocutor y del reporte en curso.

    Es el "estado por contacto" que persiste entre turnos. El borrador del reporte se completa de
    forma incremental: un turno aporta el nombre, otro el documento, etc.
    """
    declared_name: Optional[str] = None      # cómo dice llamarse el interlocutor
    intention: Optional[str] = None          # desaparecido | encontrado | autoreporte
    subject_name: Optional[str] = None       # núcleo del reporte (sujeto del reporte)
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    notes: Optional[str] = None
    turn_count: int = 0
    report_emitted: bool = False             # evita re-publicar report.received en cada turno

    @property
    def report_complete(self) -> bool:
        """¿El reporte acumulado tiene intención + núcleo obligatorio (nombre + tipo + nº id)?"""
        return bool(self.intention) and all(getattr(self, f) for f in _CORE_FIELDS)

    def merged_with(self, *, intention: Optional[str] = None, subject_name: Optional[str] = None,
                    id_type: Optional[str] = None, id_number: Optional[str] = None,
                    notes: Optional[str] = None, declared_name: Optional[str] = None
                    ) -> "SessionProfile":
        """Funde datos nuevos sin pisar lo ya conocido con valores vacíos (acumulación monotónica)."""
        return replace(
            self,
            declared_name=declared_name or self.declared_name,
            intention=intention or self.intention,
            subject_name=subject_name or self.subject_name,
            id_type=id_type or self.id_type,
            id_number=id_number or self.id_number,
            notes=notes or self.notes,
        )


@dataclass(frozen=True)
class ConversationContext:
    """Lo que el servicio carga al inicio de un turno: identidad + memoria relevante + perfil.

    - `recent`: últimos turnos textuales (coherencia conversacional).
    - `retrieved`: turnos antiguos recuperados por similitud semántica (economía del LLM: traemos
      solo lo pertinente en vez de todo el historial — ADR-0015).
    """
    key: str
    profile: SessionProfile = field(default_factory=SessionProfile)
    recent: tuple[Turn, ...] = ()
    retrieved: tuple[Turn, ...] = ()

    @property
    def is_new(self) -> bool:
        return self.profile.turn_count == 0

    def profile_summary(self) -> str:
        """Resumen compacto del perfil para inyectar en el system prompt (barato en tokens)."""
        p = self.profile
        parts = []
        if p.declared_name:
            parts.append(f"interlocutor dice llamarse {p.declared_name}")
        if p.intention:
            parts.append(f"intención: {p.intention}")
        if p.subject_name:
            parts.append(f"sujeto del reporte: {p.subject_name}")
        if p.id_type or p.id_number:
            parts.append(f"documento: {p.id_type or '?'} {p.id_number or '?'}")
        if p.notes:
            parts.append(f"notas: {p.notes}")
        return "; ".join(parts)
