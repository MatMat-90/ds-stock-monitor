"""Capture continue avec mémoire circulaire.

La caméra filme en continu, mais rien n'est écrit sur disque tant qu'aucun
événement ne se produit : les dernières secondes sont gardées en mémoire
(deque bornée). Au déclenchement, ce pré-enregistrement est combiné aux
images suivantes pour produire un extrait complet — on ne sauvegarde que
l'utile.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class BufferedFrame:
    t: float
    frame: np.ndarray


class FrameRingBuffer:
    """Conserve les `seconds` dernières secondes de vidéo en mémoire."""

    def __init__(self, seconds: float, fps: float) -> None:
        if seconds <= 0 or fps <= 0:
            raise ValueError("seconds et fps doivent être positifs")
        self.seconds = seconds
        maxlen = max(1, int(round(seconds * fps)))
        self._frames: deque[BufferedFrame] = deque(maxlen=maxlen)

    def append(self, t: float, frame: np.ndarray) -> None:
        self._frames.append(BufferedFrame(t, frame))

    def snapshot(self, since: float | None = None) -> list[BufferedFrame]:
        """Copie ordonnée du tampon, optionnellement à partir d'un instant."""
        if since is None:
            return list(self._frames)
        return [bf for bf in self._frames if bf.t >= since]

    def __len__(self) -> int:
        return len(self._frames)
