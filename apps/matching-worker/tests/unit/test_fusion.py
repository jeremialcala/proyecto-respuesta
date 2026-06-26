"""Tests de la fusión multi-señal con pesos dinámicos (ADR-0004)."""
import pytest

from matching_worker.config import FusionWeights
from matching_worker.domain import fusion
from matching_worker.domain.models import Signals

W = FusionWeights()  # face=0.6, geo=0.25, text=0.15


def test_sim_from_distance():
    assert fusion.sim_from_distance(0.0) == 1.0
    assert fusion.sim_from_distance(1.0) == 0.0
    assert fusion.sim_from_distance(0.3) == pytest.approx(0.7)


def test_fuse_all_signals():
    score = fusion.fuse(Signals(face=0.8, geo=0.6, text=0.4), W)
    assert score == pytest.approx(0.69)  # 0.6*.8+0.25*.6+0.15*.4 / 1.0


def test_dynamic_weights_drop_missing_signal():
    # sin geo → normaliza sobre face+text (0.6 y 0.15)
    score = fusion.fuse(Signals(face=0.8, geo=None, text=0.4), W)
    assert score == pytest.approx(0.54 / 0.75)


def test_only_face_present_returns_face_sim():
    assert fusion.fuse(Signals(face=0.8), W) == pytest.approx(0.8)


def test_no_signals_raises():
    with pytest.raises(ValueError):
        fusion.fuse(Signals(), W)
