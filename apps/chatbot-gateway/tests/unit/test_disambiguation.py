"""Parser de la respuesta de desambiguación multi-rostro (ADR-0016)."""
from chatbot_gateway.domain.disambiguation import parse_selection


def test_plain_number_in_range():
    s = parse_selection("2", 3)
    assert s.kind == "index" and s.index == 1   # mostrado 1..N → 0-based


def test_number_in_sentence():
    s = parse_selection("creo que es el 1", 3)
    assert s.kind == "index" and s.index == 0


def test_out_of_range_is_invalid():
    assert parse_selection("5", 3).kind == "invalid"
    assert parse_selection("0", 3).kind == "invalid"


def test_none_variants():
    for t in ["ninguno", "Ninguna de ellas", "no es ninguno", "nadie", "none"]:
        assert parse_selection(t, 3).kind == "none", t


def test_garbage_is_invalid():
    assert parse_selection("hola", 3).kind == "invalid"
    assert parse_selection("", 3).kind == "invalid"
