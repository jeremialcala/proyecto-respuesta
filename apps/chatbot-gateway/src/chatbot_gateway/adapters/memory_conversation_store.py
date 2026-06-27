"""ConversationStore en memoria (dev/tests y arranque sin Postgres). No persiste entre reinicios.

Recupera por similitud coseno sobre los embeddings de cada turno; si no hay embeddings, opera solo
con la ventana reciente. Mismo contrato que el adaptador Postgres+pgvector (ADR-0015).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..domain.conversation import ConversationContext, SessionProfile, Turn


@dataclass
class _Stored:
    turn: Turn
    embedding: tuple[float, ...]


@dataclass
class _Session:
    profile: SessionProfile = field(default_factory=SessionProfile)
    turns: list[_Stored] = field(default_factory=list)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return -1.0
    return dot / (na * nb)


class MemoryConversationStore:
    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}

    def load(self, key: str, query_embedding: Sequence[float], *,
             recent_n: int, top_k: int) -> ConversationContext:
        s = self._sessions.get(key)
        if s is None:
            return ConversationContext(key=key)

        recent = [st.turn for st in s.turns[-recent_n:]] if recent_n > 0 else []

        retrieved: list[Turn] = []
        if query_embedding and top_k > 0 and len(s.turns) > recent_n:
            older = s.turns[:-recent_n] if recent_n > 0 else s.turns
            scored = [(_cosine(query_embedding, st.embedding), st.turn)
                      for st in older if st.embedding]
            scored.sort(key=lambda t: t[0], reverse=True)
            retrieved = [turn for score, turn in scored[:top_k] if score > 0]

        return ConversationContext(key=key, profile=s.profile,
                                   recent=tuple(recent), retrieved=tuple(retrieved))

    def append_turn(self, key: str, turn: Turn, embedding: Sequence[float]) -> None:
        s = self._sessions.setdefault(key, _Session())
        s.turns.append(_Stored(turn=turn, embedding=tuple(embedding or ())))

    def save_profile(self, key: str, profile: SessionProfile) -> None:
        s = self._sessions.setdefault(key, _Session())
        s.profile = profile
