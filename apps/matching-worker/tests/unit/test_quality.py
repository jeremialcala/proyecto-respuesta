"""Tests de la compuerta de calidad (ADR-0004)."""
from matching_worker.config import QualityThresholds
from matching_worker.domain.models import FaceQuality
from matching_worker.domain.quality import passes

T = QualityThresholds()  # min_size=80, min_blur_var=40, max_yaw/pitch=45


def test_good_face_passes():
    assert passes(FaceQuality(size_px=120, blur_var=80.0, yaw=10.0, pitch=-5.0), T)


def test_small_face_fails():
    assert not passes(FaceQuality(size_px=40, blur_var=80.0, yaw=0.0, pitch=0.0), T)


def test_blurry_face_fails():
    assert not passes(FaceQuality(size_px=120, blur_var=10.0, yaw=0.0, pitch=0.0), T)


def test_extreme_pose_fails():
    assert not passes(FaceQuality(size_px=120, blur_var=80.0, yaw=70.0, pitch=0.0), T)
