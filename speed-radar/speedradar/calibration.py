"""Auto-calibration de la caméra.

Deux modes, du plus simple au plus précis :

1. **Auto-calibration statistique** (`AutoCalibrator`) — aucune intervention.
   Les véhicules qui traversent le champ servent d'étalon : la longueur
   moyenne d'un véhicule léger est connue (~4,4 m). En mesurant la longueur
   apparente (pixels) de chaque véhicule le long de sa direction de
   déplacement, on obtient des échantillons mètres/pixel. Comme l'échelle
   varie avec la profondeur de la scène, les échantillons sont agrégés par
   bandes horizontales de l'image (médiane par bande) puis interpolés.
   Après quelques dizaines de passages, l'échelle converge.

2. **Homographie sol** (`PlanarCalibration`) — l'utilisateur fournit au moins
   4 correspondances entre pixels de l'image et coordonnées métriques au sol
   (marquages routiers, longueur de bandes blanches...). Précision bien
   meilleure ; utilisée automatiquement si `calibration.ground_points` est
   renseigné dans la configuration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class ScaleSample:
    """Un échantillon d'échelle observé sur un véhicule en mouvement."""

    y: float  # position verticale (px) du centre du véhicule
    meters_per_pixel: float


class AutoCalibrator:
    """Estime l'échelle mètres/pixel par bande horizontale de l'image."""

    def __init__(
        self,
        frame_height: int,
        mean_vehicle_length_m: float = 4.4,
        bands: int = 8,
        min_samples: int = 30,
    ) -> None:
        if frame_height <= 0:
            raise ValueError("frame_height doit être positif")
        self.frame_height = frame_height
        self.mean_vehicle_length_m = mean_vehicle_length_m
        self.bands = max(1, bands)
        self.min_samples = min_samples
        self._samples: list[ScaleSample] = []

    # ------------------------------------------------------------------
    # Alimentation
    # ------------------------------------------------------------------
    def observe(
        self,
        bbox: tuple[float, float, float, float],
        motion_vector: tuple[float, float],
    ) -> None:
        """Ajoute une observation: boîte englobante (x, y, w, h) d'un véhicule
        et son vecteur de déplacement (dx, dy) en pixels.

        La longueur apparente du véhicule est l'étendue de sa boîte projetée
        sur la direction du mouvement (les véhicules se déplacent selon leur
        axe longitudinal).
        """
        x, y, w, h = bbox
        dx, dy = motion_vector
        norm = math.hypot(dx, dy)
        if norm < 1e-6 or w <= 0 or h <= 0:
            return
        ux, uy = dx / norm, dy / norm
        length_px = abs(w * ux) + abs(h * uy)
        if length_px < 4:  # trop petit pour être fiable
            return
        cy = y + h / 2.0
        self._samples.append(ScaleSample(cy, self.mean_vehicle_length_m / length_px))

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------
    @property
    def sample_count(self) -> int:
        return len(self._samples)

    @property
    def is_calibrated(self) -> bool:
        return len(self._samples) >= self.min_samples

    def _band_medians(self) -> tuple[np.ndarray, np.ndarray]:
        """Médiane des échantillons par bande -> (centres_y, échelles)."""
        band_h = self.frame_height / self.bands
        centers, scales = [], []
        for b in range(self.bands):
            lo, hi = b * band_h, (b + 1) * band_h
            vals = [s.meters_per_pixel for s in self._samples if lo <= s.y < hi]
            if vals:
                centers.append(lo + band_h / 2.0)
                scales.append(float(np.median(vals)))
        return np.asarray(centers), np.asarray(scales)

    def scale_at(self, y: float) -> float:
        """Échelle mètres/pixel à la position verticale `y` (interpolée)."""
        if not self._samples:
            raise RuntimeError("Aucun échantillon de calibration")
        centers, scales = self._band_medians()
        if len(centers) == 1:
            return float(scales[0])
        return float(np.interp(y, centers, scales))

    def summary(self) -> dict:
        """État de la calibration, pour le relevé et les journaux."""
        centers, scales = (
            self._band_medians() if self._samples else (np.array([]), np.array([]))
        )
        return {
            "samples": self.sample_count,
            "calibrated": self.is_calibrated,
            "bands": [
                {"y": float(c), "meters_per_pixel": float(s)}
                for c, s in zip(centers, scales)
            ],
        }


def homography_from_points(points: list[list[float]]) -> np.ndarray:
    """Calcule l'homographie image -> sol par DLT normalisé.

    `points`: liste de [px_x, px_y, sol_x_m, sol_y_m], au moins 4 entrées.
    """
    if len(points) < 4:
        raise ValueError("Au moins 4 correspondances sont nécessaires")
    src = np.asarray([[p[0], p[1]] for p in points], dtype=float)
    dst = np.asarray([[p[2], p[3]] for p in points], dtype=float)

    def normalize(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mean = pts.mean(axis=0)
        centered = pts - mean
        rms = np.sqrt((centered**2).sum(axis=1).mean())
        scale = math.sqrt(2) / max(rms, 1e-12)
        T = np.array(
            [[scale, 0, -scale * mean[0]], [0, scale, -scale * mean[1]], [0, 0, 1]]
        )
        homog = np.column_stack([pts, np.ones(len(pts))])
        return (T @ homog.T).T[:, :2], T

    src_n, T_src = normalize(src)
    dst_n, T_dst = normalize(dst)

    rows = []
    for (sx, sy), (dx_, dy_) in zip(src_n, dst_n):
        rows.append([-sx, -sy, -1, 0, 0, 0, dx_ * sx, dx_ * sy, dx_])
        rows.append([0, 0, 0, -sx, -sy, -1, dy_ * sx, dy_ * sy, dy_])
    A = np.asarray(rows)
    _, _, vt = np.linalg.svd(A)
    Hn = vt[-1].reshape(3, 3)
    H = np.linalg.inv(T_dst) @ Hn @ T_src
    return H / H[2, 2]


@dataclass
class PlanarCalibration:
    """Projection image -> plan du sol via homographie fournie par l'utilisateur."""

    H: np.ndarray = field(repr=False)

    @classmethod
    def from_ground_points(cls, points: list[list[float]]) -> "PlanarCalibration":
        return cls(H=homography_from_points(points))

    def to_ground(self, px: float, py: float) -> tuple[float, float]:
        """Projette un pixel sur le plan du sol (coordonnées en mètres)."""
        v = self.H @ np.array([px, py, 1.0])
        return float(v[0] / v[2]), float(v[1] / v[2])
