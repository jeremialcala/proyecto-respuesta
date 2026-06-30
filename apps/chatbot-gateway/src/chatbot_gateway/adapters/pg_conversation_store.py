"""ConversationStore sobre Postgres + pgvector (ADR-0015). `psycopg` perezoso (como core-backend).

Dos tablas:
- `chat_sessions`: perfil de sesión por contacto (clave hash), `profile` en JSONB.
- `chat_turns`: historial de turnos con `embedding vector(N)` para recuperación semántica.

Economía del LLM: en vez de mandar todo el historial cada turno, recuperamos la ventana reciente
(por `seq`) + los `top_k` turnos más similares al mensaje actual (operador `<=>`, distancia coseno).

Retención (ADR-0006/0007): los turnos son datos de conversación efímeros; se purgan por edad con
`purge_older_than` (lo invoca un job programado, fuera de esta clase).
"""
from __future__ import annotations

import json
from typing import Sequence

from ..domain.conversation import ConversationContext, SessionProfile, Turn

_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chat_sessions (
  conv_key text PRIMARY KEY,
  profile jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chat_turns (
  conv_key text NOT NULL,
  seq bigint NOT NULL,
  role text NOT NULL,
  text text NOT NULL,
  embedding vector({dim}),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (conv_key, seq)
);
CREATE INDEX IF NOT EXISTS chat_turns_recent ON chat_turns (conv_key, seq DESC);
"""

# Debe incluir TODOS los campos persistibles del perfil: si falta uno (p. ej. `location`) se pierde al
# guardar/cargar entre turnos. `last_closed_ref` reemplaza al antiguo `completion_notified`.
_PROFILE_FIELDS = ("declared_name", "intention", "subject_name", "id_type", "id_number",
                   "location", "notes", "turn_count", "report_emitted", "last_closed_ref",
                   "photo_retry_count", "pending_disambiguation_id", "pending_faces_count")


def _profile_to_json(p: SessionProfile) -> str:
    return json.dumps({f: getattr(p, f) for f in _PROFILE_FIELDS})


def _profile_from_json(d: dict) -> SessionProfile:
    return SessionProfile(**{f: d.get(f) for f in _PROFILE_FIELDS if d.get(f) is not None})


def _vec(embedding: Sequence[float]) -> str | None:
    if not embedding:
        return None
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


class PgConversationStore:
    def __init__(self, dsn: str, embed_dim: int = 768) -> None:
        self._dsn = dsn
        self._dim = embed_dim
        self._conn = None

    def _c(self):
        if self._conn is None:
            import psycopg
            self._conn = psycopg.connect(self._dsn, autocommit=True)
        return self._conn

    def init_schema(self) -> None:
        self._c().execute(_DDL.format(dim=self._dim))

    def load(self, key: str, query_embedding: Sequence[float], *,
             recent_n: int, top_k: int) -> ConversationContext:
        c = self._c()
        row = c.execute("SELECT profile FROM chat_sessions WHERE conv_key=%s", (key,)).fetchone()
        if row is None:
            return ConversationContext(key=key)
        profile = _profile_from_json(row[0] or {})

        recent_rows = c.execute(
            "SELECT seq, role, text, created_at FROM chat_turns WHERE conv_key=%s"
            " ORDER BY seq DESC LIMIT %s", (key, recent_n)).fetchall()
        recent_rows.reverse()   # cronológico
        recent = tuple(Turn(role=r[1], text=r[2], ts=_iso(r[3])) for r in recent_rows)
        recent_seqs = [r[0] for r in recent_rows]

        retrieved: tuple[Turn, ...] = ()
        q = _vec(query_embedding)
        if q is not None and top_k > 0:
            exclude = tuple(recent_seqs) or (-1,)
            sql = ("SELECT role, text, created_at FROM chat_turns"
                   " WHERE conv_key=%s AND embedding IS NOT NULL AND seq <> ALL(%s)"
                   " ORDER BY embedding <=> %s LIMIT %s")
            rows = c.execute(sql, (key, list(exclude), q, top_k)).fetchall()
            retrieved = tuple(Turn(role=r[0], text=r[1], ts=_iso(r[2])) for r in rows)

        return ConversationContext(key=key, profile=profile, recent=recent, retrieved=retrieved)

    def append_turn(self, key: str, turn: Turn, embedding: Sequence[float]) -> None:
        c = self._c()
        c.execute("INSERT INTO chat_sessions (conv_key) VALUES (%s) ON CONFLICT DO NOTHING", (key,))
        seq = int(c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM chat_turns WHERE conv_key=%s",
                            (key,)).fetchone()[0])
        c.execute("INSERT INTO chat_turns (conv_key, seq, role, text, embedding)"
                  " VALUES (%s,%s,%s,%s,%s)", (key, seq, turn.role, turn.text, _vec(embedding)))

    def save_profile(self, key: str, profile: SessionProfile) -> None:
        self._c().execute(
            "INSERT INTO chat_sessions (conv_key, profile, updated_at) VALUES (%s,%s, now())"
            " ON CONFLICT (conv_key) DO UPDATE SET profile=EXCLUDED.profile, updated_at=now()",
            (key, _profile_to_json(profile)))

    def purge_older_than(self, days: int) -> None:
        """Retención: borra conversaciones inactivas (ADR-0006/0007). Lo invoca un job programado."""
        c = self._c()
        c.execute("DELETE FROM chat_turns WHERE created_at < now() - make_interval(days => %s)", (days,))
        c.execute("DELETE FROM chat_sessions WHERE updated_at < now() - make_interval(days => %s)", (days,))


def _iso(dt) -> str:
    try:
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except AttributeError:
        return str(dt or "")
