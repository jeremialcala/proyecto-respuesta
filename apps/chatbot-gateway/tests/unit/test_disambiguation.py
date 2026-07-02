"""Parser de la respuesta de desambiguación multi-rostro (ADR-0016) y otros rostros (ADR-0021)."""
from chatbot_gateway.domain.disambiguation import (parse_multi_selection, parse_selection,
                                                   parse_yes_no)


def test_multi_selection_several_numbers():
    s = parse_multi_selection("el 1 y el 3", 3)
    assert s.kind == "indices" and s.indices == (0, 2)


def test_multi_selection_dedupes_and_orders_and_filters_range():
    s = parse_multi_selection("2, 2, 5, 1", 3)     # 5 fuera de rango; 2 duplicado
    assert s.kind == "indices" and s.indices == (1, 0)


def test_multi_selection_none_and_all_and_invalid():
    assert parse_multi_selection("ninguno", 3).kind == "none"
    assert parse_multi_selection("todos", 3).indices == (0, 1, 2)
    assert parse_multi_selection("no sé", 3).kind == "invalid"


def test_yes_no():
    assert parse_yes_no("sí, claro") == "yes"
    assert parse_yes_no("no") == "no"
    assert parse_yes_no("quizás") == "invalid"


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
