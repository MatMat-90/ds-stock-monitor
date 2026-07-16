"""Estimation de la vitesse d'une piste à partir de la calibration.

La vitesse est obtenue par régression linéaire de la distance cumulée au sol
en fonction du temps (robuste au bruit de détection image par image), avec un
score de qualité (R²) qui permet d'écarter les mesures douteuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .calibration import AutoCalibrator, PlanarCalibration
from .tracking import Track


@dataclass
class SpeedEstimate:
    kmh: float
    quality: float  # R² de la régression, entre 0 et 1
    distance_m: float
    duration_s: float


def _ground_positions_planar(track: Track, cal: PlanarCalibration) -> np.ndarray:
    pts = []
    for p in track.points:
        x, y, w, h = p.bbox
        gx, gy = cal.to_ground(x + w / 2.0, y + h)
        pts.append((gx, gy))
    return np.asarray(pts)


def _cumulative_distance_scaled(track: Track, cal: AutoCalibrator) -> np.ndarray:
    """Distance cumulée (m) avec une échelle m/px dépendant de la hauteur image."""
    dist = [0.0]
    for a, b in zip(track.points, track.points[1:]):
        y_mid = (a.cy + b.cy) / 2.0
        scale = cal.scale_at(y_mid)
        step_px = np.hypot(b.cx - a.cx, b.cy - a.cy)
        dist.append(dist[-1] + step_px * scale)
    return np.asarray(dist)


def estimate_speed(
    track: Track,
    calibrator: AutoCalibrator | None = None,
    planar: PlanarCalibration | None = None,
    min_points: int = 8,
) -> Optional[SpeedEstimate]:
    """Vitesse d'une piste, ou None si la mesure n'est pas exploitable.

    L'homographie (`planar`) est utilisée en priorité si disponible, sinon
    l'auto-calibration statistique (`calibrator`).
    """
    if len(track.points) < min_points:
        return None

    times = np.asarray([p.t for p in track.points])
    duration = float(times[-1] - times[0])
    if duration <= 0:
        return None

    if planar is not None:
        ground = _ground_positions_planar(track, planar)
        steps = np.linalg.norm(np.diff(ground, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(steps)])
    elif calibrator is not None and calibrator.is_calibrated:
        cum = _cumulative_distance_scaled(track, calibrator)
    else:
        return None

    # Régression linéaire distance = v * t + b
    t = times - times[0]
    A = np.column_stack([t, np.ones_like(t)])
    (v_ms, _), residuals, *_ = np.linalg.lstsq(A, cum, rcond=None)
    ss_tot = float(((cum - cum.mean()) ** 2).sum())
    ss_res = float(residuals[0]) if len(residuals) else 0.0
    quality = 1.0 if ss_tot < 1e-12 else max(0.0, 1.0 - ss_res / ss_tot)

    if v_ms < 0:
        return None
    return SpeedEstimate(
        kmh=float(v_ms * 3.6),
        quality=quality,
        distance_m=float(cum[-1]),
        duration_s=duration,
    )
