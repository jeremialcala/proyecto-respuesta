"""Auditoría append-only con encadenamiento SHA-256 (ADR-0007)."""
from core_backend.domain.audit import make_entry, verify_chain, GENESIS


def _chain(n):
    entries, prev = [], GENESIS
    for i in range(1, n + 1):
        e = make_entry(i, "actor", "action", {"i": i}, prev)
        entries.append(e); prev = e.hash
    return entries


def test_chain_verifies():
    assert verify_chain(_chain(3)) is True


def test_first_links_to_genesis():
    e = _chain(1)[0]
    assert e.prev_hash == GENESIS and len(e.hash) == 64


def test_tamper_breaks_chain():
    import dataclasses
    entries = _chain(3)
    entries[1] = dataclasses.replace(entries[1], payload={"i": 999})  # alterar un registro
    assert verify_chain(entries) is False


def test_deterministic_hash():
    a = make_entry(1, "x", "y", {"k": 1}, GENESIS)
    b = make_entry(1, "x", "y", {"k": 1}, GENESIS)
    assert a.hash == b.hash
