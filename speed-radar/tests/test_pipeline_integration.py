"""Test d'intégration : une vidéo synthétique traverse tout le pipeline
(détection -> suivi -> auto-calibration -> vitesse -> extrait -> relevé)."""

import numpy as np
import pytest

from speedradar.config import RadarConfig
from speedradar.events import EventLog
from speedradar.pipeline import SpeedRadar
from speedradar.ring_buffer import FrameRingBuffer

FPS = 25.0
W, H = 640, 360
CAR_W, CAR_H = 110, 50
PX_PER_FRAME = 8.0  # 8 px/img * 25 i/s * 0,04 m/px = 8 m/s = 28,8 km/h


def background() -> np.ndarray:
    rng = np.random.default_rng(42)
    bg = np.full((H, W, 3), 120, dtype=np.uint8)
    noise = rng.integers(-8, 8, size=(H, W, 1), dtype=np.int16)
    return np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def frame_with_car(bg: np.ndarray, x: float, y: int = 180) -> np.ndarray:
    f = bg.copy()
    x0 = int(x)
    if x0 + CAR_W > 0 and x0 < W:
        a, b = max(0, x0), min(W, x0 + CAR_W)
        f[y : y + CAR_H, a:b] = (30, 30, 200)
    return f


@pytest.fixture
def radar(tmp_path):
    cfg = RadarConfig()
    cfg.detection.prefer_yolo = False
    cfg.detection.min_area = 1000
    cfg.calibration.min_samples = 10
    cfg.tracking.min_track_points = 8
    cfg.speed_limit_kmh = 10.0  # seuil bas: le passage synthétique déclenche
    cfg.tolerance_kmh = 0.0
    cfg.recording.output_dir = str(tmp_path / "captures")
    cfg.recording.pre_seconds = 1.0
    cfg.recording.post_seconds = 0.3
    return SpeedRadar(cfg)


def run_pass(radar, ring, bg, t0: float, n_frames: int = 70) -> float:
    """Fait traverser un véhicule de gauche à droite; retourne le temps final."""
    t = t0
    for i in range(n_frames):
        x = -CAR_W + i * PX_PER_FRAME
        radar.process_frame(t, frame_with_car(bg, x), ring, FPS)
        t += 1.0 / FPS
    return t


def test_full_pipeline_detects_measures_and_records(radar, tmp_path):
    bg = background()
    ring = FrameRingBuffer(1.0, FPS)

    # Apprentissage du fond par MOG2.
    t = 0.0
    for _ in range(40):
        radar.process_frame(t, bg.copy(), ring, FPS)
        t += 1.0 / FPS

    # Premier passage : alimente l'auto-calibration.
    t = run_pass(radar, ring, bg, t)
    assert radar.calibrator.sample_count > 0

    # Passages suivants : calibration atteinte puis mesure + déclenchement.
    for _ in range(3):
        t = run_pass(radar, ring, bg, t)
    assert radar.calibrator.is_calibrated

    # Laisse le post-roll se terminer.
    for _ in range(30):
        radar.process_frame(t, bg.copy(), ring, FPS)
        t += 1.0 / FPS

    events = EventLog(tmp_path / "captures" / "releves.jsonl").read_all()
    assert events, "au moins un relevé attendu"
    event = events[0]
    # 28,8 km/h théoriques; l'auto-calibration statistique tolère ±40 %.
    assert event.speed_kmh == pytest.approx(28.8, rel=0.4)
    assert event.is_violation
    assert event.clip_path and (tmp_path / "captures").exists()
    from pathlib import Path

    assert Path(event.clip_path).stat().st_size > 0
    assert Path(event.snapshot_path).stat().st_size > 0
    assert event.calibration["mode"] == "auto"
