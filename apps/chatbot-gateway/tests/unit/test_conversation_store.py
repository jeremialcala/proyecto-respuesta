"""MemoryConversationStore: ventana reciente + recuperación semántica + perfil (ADR-0015)."""
from chatbot_gateway.adapters.memory_conversation_store import MemoryConversationStore
from chatbot_gateway.domain.conversation import SessionProfile, Turn, conversation_key


def _emb(*vals):
    return list(vals)


def test_conversation_key_stable_and_non_reversible():
    k1 = conversation_key("bot-1", "whatsapp", "584120000000")
    k2 = conversation_key("bot-1", "whatsapp", "584120000000")
    assert k1 == k2 and len(k1) == 64           # sha-256 hex
    assert "584120000000" not in k1             # no expone el handle crudo
    assert conversation_key("bot-1", "whatsapp", "otro") != k1


def test_new_conversation_returns_empty_context():
    store = MemoryConversationStore()
    ctx = store.load("k", _emb(1.0, 0.0), recent_n=6, top_k=4)
    assert ctx.is_new and ctx.recent == () and ctx.retrieved == ()


def test_recent_window_is_chronological_and_capped():
    store = MemoryConversationStore()
    for i in range(5):
        store.append_turn("k", Turn(role="user", text=f"m{i}"), _emb(0.0, 0.0))
    ctx = store.load("k", _emb(0.0, 0.0), recent_n=3, top_k=0)
    assert [t.text for t in ctx.recent] == ["m2", "m3", "m4"]   # últimos 3, en orden


def test_semantic_retrieval_brings_relevant_old_turn():
    store = MemoryConversationStore()
    # Turno antiguo relevante a la consulta (vector alineado) + ruido; luego ventana reciente.
    store.append_turn("k", Turn(role="user", text="relevante"), _emb(1.0, 0.0))
    store.append_turn("k", Turn(role="user", text="ruido"), _emb(0.0, 1.0))
    for i in range(6):
        store.append_turn("k", Turn(role="user", text=f"reciente{i}"), _emb(0.0, 0.0))
    ctx = store.load("k", _emb(1.0, 0.0), recent_n=6, top_k=1)
    assert len(ctx.retrieved) == 1 and ctx.retrieved[0].text == "relevante"


def test_profile_roundtrip():
    store = MemoryConversationStore()
    store.save_profile("k", SessionProfile(subject_name="Juan", intention="desaparecido", turn_count=2))
    ctx = store.load("k", [], recent_n=6, top_k=4)
    assert ctx.profile.subject_name == "Juan" and ctx.profile.turn_count == 2
