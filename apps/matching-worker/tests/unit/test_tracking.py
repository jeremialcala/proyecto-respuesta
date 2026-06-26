"""Tests de la agrupación por track en video (ADR-0004)."""
from matching_worker.config import DriftParams, TrackingParams
from matching_worker.domain.tracking import reid_is_stricter_than_match, should_join

TP = TrackingParams()  # reid_distance=0.45, min_iou=0.30


def test_join_by_spatial_continuity():
    assert should_join(distance=0.9, iou=0.5, p=TP) is True  # alto IoU


def test_join_by_reid_embedding():
    assert should_join(distance=0.40, iou=0.0, p=TP) is True  # distancia < reid


def test_no_join_when_far_and_no_overlap():
    assert should_join(distance=0.50, iou=0.1, p=TP) is False


def test_reid_threshold_stricter_than_match():
    """Invariante: agrupar por track es más estricto que el match cruzado (reid < tau0)."""
    assert reid_is_stricter_than_match(TP, DriftParams()) is True
