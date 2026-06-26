"""Tests de la tolerancia a drift (ADR-0004). Incluye el invariante: el face-match nunca auto-confirma."""
from matching_worker.config import DriftParams
from matching_worker.domain import drift
from matching_worker.domain.models import Band, Routing

P = DriftParams()  # tau0=0.6, alpha=0.015, beta=0.10, delta_max=0.15


def test_band_strong_below_tau0():
    assert drift.compute_band(0.5, age_gap_years=0, is_minor=False, p=P) is Band.STRONG


def test_band_drift_tolerated_within_margin():
    # age_gap=4 → margin=0.06 → ventana (0.6, 0.66]
    assert drift.compute_band(0.63, age_gap_years=4, is_minor=False, p=P) is Band.DRIFT_TOLERATED


def test_band_discard_beyond_margin():
    assert drift.compute_band(0.70, age_gap_years=4, is_minor=False, p=P) is Band.DISCARD


def test_drift_margin_grows_with_gap_and_minor_and_caps():
    assert drift.drift_margin(4, False, P) == 0.06
    assert drift.drift_margin(4, True, P) == 0.15   # 0.06+0.10=0.16 → cap 0.15
    assert drift.drift_margin(100, False, P) == 0.15  # cap


def test_route_invariants():
    # drift tolerado → siempre coordinador (nunca auto)
    assert drift.route(Band.DRIFT_TOLERATED, is_minor=False) is Routing.COORDINATOR
    # strong + adulto → continúa a fusión (no es auto-confirmación)
    assert drift.route(Band.STRONG, is_minor=False) is Routing.FUSE
    # strong + menor → siempre coordinador
    assert drift.route(Band.STRONG, is_minor=True) is Routing.COORDINATOR
    # descarte
    assert drift.route(Band.DISCARD, is_minor=False) is Routing.DISCARD


def test_drift_tolerated_never_routes_to_fuse():
    """Un match que solo pasa por tolerancia de drift NUNCA va por la vía automática."""
    for minor in (False, True):
        assert drift.route(Band.DRIFT_TOLERATED, is_minor=minor) is Routing.COORDINATOR
