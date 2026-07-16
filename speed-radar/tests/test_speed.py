import pytest

from speedradar.calibration import AutoCalibrator, PlanarCalibration
from speedradar.speed import estimate_speed
from speedradar.tracking import Track, TrackPoint


def build_track(px_per_frame: float, fps: float = 25.0, n: int = 20, y: float = 360.0):
    """Piste synthétique à vitesse constante, mouvement horizontal."""
    track = Track(track_id=1)
    for i in range(n):
        cx = 100 + i * px_per_frame
        track.points.append(TrackPoint(i / fps, cx, y, (cx - 55, y - 27, 110, 55)))
    return track


def calibrated(scale_m_per_px: float, y: float = 360.0) -> AutoCalibrator:
    cal = AutoCalibrator(frame_height=720, mean_vehicle_length_m=4.4, min_samples=5)
    length_px = 4.4 / scale_m_per_px
    for _ in range(10):
        cal.observe((300, y - 27, length_px, length_px / 2), (10.0, 0.0))
    return cal


def test_constant_speed_with_autocalibration():
    # 0,04 m/px, 10 px/image à 25 i/s -> 0,4 m * 25 = 10 m/s = 36 km/h
    cal = calibrated(0.04)
    est = estimate_speed(build_track(10.0), calibrator=cal)
    assert est is not None
    assert est.kmh == pytest.approx(36.0, rel=0.05)
    assert est.quality > 0.99


def test_constant_speed_with_homography():
    # 1 px = 0,1 m au sol ; 20 px/image à 25 i/s -> 2 m * 25 = 50 m/s = 180 km/h
    planar = PlanarCalibration.from_ground_points(
        [[0, 0, 0, 0], [100, 0, 10, 0], [100, 100, 10, 10], [0, 100, 0, 10]]
    )
    est = estimate_speed(build_track(20.0), planar=planar)
    assert est is not None
    assert est.kmh == pytest.approx(180.0, rel=0.05)


def test_short_track_rejected():
    cal = calibrated(0.04)
    est = estimate_speed(build_track(10.0, n=4), calibrator=cal, min_points=8)
    assert est is None


def test_uncalibrated_returns_none():
    cal = AutoCalibrator(frame_height=720, min_samples=50)  # jamais atteint
    est = estimate_speed(build_track(10.0), calibrator=cal)
    assert est is None


def test_stationary_object_speed_near_zero():
    cal = calibrated(0.04)
    est = estimate_speed(build_track(0.0), calibrator=cal)
    assert est is not None
    assert est.kmh == pytest.approx(0.0, abs=0.5)


def test_noisy_track_quality_below_perfect():
    """Un bruit de détection doit dégrader le score de qualité, pas la moyenne."""
    cal = calibrated(0.04)
    track = build_track(10.0)
    for i, p in enumerate(track.points):
        p.cx += (-1) ** i * 3.0  # bruit alterné de ±3 px
    est = estimate_speed(track, calibrator=cal)
    assert est is not None
    assert est.kmh == pytest.approx(36.0, rel=0.25)
    assert est.quality < 1.0
