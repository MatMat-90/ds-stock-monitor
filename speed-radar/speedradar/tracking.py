"""Suivi multi-objets par association de centroïdes.

Volontairement simple et sans dépendance lourde : chaque détection est
associée à la piste existante la plus proche (distance euclidienne bornée).
Chaque piste conserve son historique horodaté (position, boîte) qui sert à
la fois à l'estimation de vitesse et à l'auto-calibration.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

BBox = tuple[float, float, float, float]  # x, y, w, h


@dataclass
class TrackPoint:
    t: float
    cx: float
    cy: float
    bbox: BBox


@dataclass
class Track:
    track_id: int
    points: list[TrackPoint] = field(default_factory=list)
    missed: int = 0

    @property
    def last(self) -> TrackPoint:
        return self.points[-1]

    @property
    def ground_point(self) -> tuple[float, float]:
        """Point de contact au sol estimé : milieu du bord bas de la boîte."""
        x, y, w, h = self.last.bbox
        return (x + w / 2.0, y + h)

    def motion_vector(self) -> tuple[float, float]:
        """Déplacement global (px) entre le premier et le dernier point."""
        if len(self.points) < 2:
            return (0.0, 0.0)
        first, last = self.points[0], self.points[-1]
        return (last.cx - first.cx, last.cy - first.cy)


class CentroidTracker:
    """Associe les détections image par image et gère le cycle de vie des pistes."""

    def __init__(self, max_distance: float = 120.0, max_missed: int = 10) -> None:
        self.max_distance = max_distance
        self.max_missed = max_missed
        self._next_id = itertools.count(1)
        self.tracks: dict[int, Track] = {}

    def update(self, t: float, detections: list[BBox]) -> tuple[list[Track], list[Track]]:
        """Met à jour les pistes avec les détections de l'instant `t`.

        Retourne (pistes_actives, pistes_closes_à_cette_itération).
        """
        centroids = [(x + w / 2.0, y + h / 2.0) for x, y, w, h in detections]

        # Association gloutonne du couple (piste, détection) le plus proche.
        pairs: list[tuple[float, int, int]] = []
        for tid, track in self.tracks.items():
            for di, (cx, cy) in enumerate(centroids):
                d = math.hypot(track.last.cx - cx, track.last.cy - cy)
                if d <= self.max_distance:
                    pairs.append((d, tid, di))
        pairs.sort()

        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        for d, tid, di in pairs:
            if tid in used_tracks or di in used_dets:
                continue
            used_tracks.add(tid)
            used_dets.add(di)
            cx, cy = centroids[di]
            track = self.tracks[tid]
            track.points.append(TrackPoint(t, cx, cy, detections[di]))
            track.missed = 0

        # Nouvelles pistes pour les détections orphelines.
        for di, (cx, cy) in enumerate(centroids):
            if di in used_dets:
                continue
            tid = next(self._next_id)
            self.tracks[tid] = Track(tid, [TrackPoint(t, cx, cy, detections[di])])

        # Pistes non revues : incrément du compteur, clôture au-delà du seuil.
        finished: list[Track] = []
        for tid in list(self.tracks):
            if tid in used_tracks or len(self.tracks[tid].points) == 0:
                continue
            track = self.tracks[tid]
            if track.last.t < t:  # pas vue à cette itération
                track.missed += 1
                if track.missed > self.max_missed:
                    finished.append(self.tracks.pop(tid))

        return list(self.tracks.values()), finished
