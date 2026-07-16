"""Écriture des extraits vidéo d'événement (pré-roll + post-roll)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .ring_buffer import BufferedFrame, FrameRingBuffer


class EventRecorder:
    """Assemble et écrit l'extrait vidéo d'un événement.

    Cycle de vie :
      1. `start(ring_buffer)` — récupère le pré-enregistrement en mémoire ;
      2. `add(t, frame)` — reçoit les images pendant et après l'événement ;
      3. `save(path)` — écrit le MP4 une fois le post-roll écoulé.
    """

    def __init__(self, fps: float, post_seconds: float = 3.0) -> None:
        self.fps = fps
        self.post_seconds = post_seconds
        self._frames: list[BufferedFrame] = []
        self._event_end_t: float | None = None

    def start(self, ring_buffer: FrameRingBuffer) -> None:
        self._frames = ring_buffer.snapshot()
        self._event_end_t = None

    def mark_event_end(self, t: float) -> None:
        """Signale la fin de l'événement (le véhicule est sorti du champ)."""
        self._event_end_t = t

    def add(self, t: float, frame: np.ndarray) -> None:
        self._frames.append(BufferedFrame(t, frame))

    @property
    def post_roll_done(self) -> bool:
        if self._event_end_t is None or not self._frames:
            return False
        return self._frames[-1].t - self._event_end_t >= self.post_seconds

    def save(self, path: str | Path) -> Path:
        if not self._frames:
            raise RuntimeError("Aucune image à enregistrer")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        h, w = self._frames[0].frame.shape[:2]
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h)
        )
        try:
            for bf in self._frames:
                writer.write(bf.frame)
        finally:
            writer.release()
        return path
