import numpy as np
import pytest

from speedradar.calibration import (
    AutoCalibrator,
    PlanarCalibration,
    homography_from_points,
)


def test_autocalibrator_converges_on_known_scale():
    """Des véhicules de 4,4 m mesurant 110 px -> échelle attendue 0,04 m/px."""
    cal = AutoCalibrator(frame_height=720, mean_vehicle_length_m=4.4, min_samples=10)
    for i in range(20):
        # Déplacement horizontal, boîte de 110 px de large, autour de y=360.
        cal.observe((300, 340 + (i % 5), 110, 55), (12.0, 0.0))
    assert cal.is_calibrated
    assert cal.scale_at(360) == pytest.approx(4.4 / 110, rel=0.05)


def test_autocalibrator_scale_varies_with_depth():
    """Les véhicules lointains (haut de l'image) paraissent plus petits :
    l'échelle m/px doit y être plus grande."""
    cal = AutoCalibrator(frame_height=800, bands=4, min_samples=10)
    for _ in range(10):
        cal.observe((100, 80, 50, 25), (10.0, 0.0))   # loin: 50 px
        cal.observe((100, 680, 200, 100), (10.0, 0.0))  # près: 200 px
    assert cal.scale_at(100) > cal.scale_at(700)


def test_autocalibrator_ignores_degenerate_observations():
    cal = AutoCalibrator(frame_height=720)
    cal.observe((0, 0, 100, 50), (0.0, 0.0))  # pas de mouvement
    cal.observe((0, 0, 2, 1), (10.0, 0.0))  # trop petit
    assert cal.sample_count == 0


def test_autocalibrator_requires_min_samples():
    cal = AutoCalibrator(frame_height=720, min_samples=5)
    for _ in range(4):
        cal.observe((100, 300, 100, 50), (10.0, 0.0))
    assert not cal.is_calibrated
    cal.observe((100, 300, 100, 50), (10.0, 0.0))
    assert cal.is_calibrated


def test_autocalibrator_caches_and_updates_on_observe():
    """scale_at doit refléter les nouvelles observations (cache invalidé)."""
    cal = AutoCalibrator(frame_height=720, bands=1, min_samples=1)
    for _ in range(5):
        cal.observe((100, 300, 100, 50), (10.0, 0.0))  # 4.4/100 = 0.044
    first = cal.scale_at(360)
    assert first == pytest.approx(0.044, rel=1e-6)
    for _ in range(50):
        cal.observe((100, 300, 200, 100), (10.0, 0.0))  # 4.4/200 = 0.022
    # La médiane bascule vers les nouvelles valeurs -> le cache s'est invalidé.
    assert cal.scale_at(360) < first


def test_autocalibrator_bounded_window():
    """La fenêtre glissante borne la mémoire; sample_count compte le total vu."""
    cal = AutoCalibrator(frame_height=720, min_samples=10, max_samples=100)
    for _ in range(500):
        cal.observe((100, 300, 100, 50), (10.0, 0.0))
    assert cal.sample_count == 500          # total observé
    assert len(cal._samples) == 100         # mémoire bornée
    assert cal.is_calibrated


def test_homography_identity():
    pts = [[0, 0, 0, 0], [100, 0, 100, 0], [100, 100, 100, 100], [0, 100, 0, 100]]
    H = homography_from_points(pts)
    assert np.allclose(H, np.eye(3), atol=1e-8)


def test_homography_scale_and_projection():
    """Un carré de 100 px correspondant à 5 m au sol."""
    pts = [[0, 0, 0, 0], [100, 0, 5, 0], [100, 100, 5, 5], [0, 100, 0, 5]]
    cal = PlanarCalibration.from_ground_points(pts)
    gx, gy = cal.to_ground(50, 50)
    assert gx == pytest.approx(2.5)
    assert gy == pytest.approx(2.5)


def test_homography_needs_four_points():
    with pytest.raises(ValueError):
        homography_from_points([[0, 0, 0, 0], [1, 0, 1, 0], [1, 1, 1, 1]])
