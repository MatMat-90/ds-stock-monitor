"""Identification du modèle de véhicule par comparaison avec des fichiers de référence.

Si l'utilisateur dépose des images de référence dans `data/vehicles/<marque_modele>/`,
chaque véhicule capturé est comparé à cette base par appariement de points
d'intérêt ORB. Sans fichiers de référence, l'identification est simplement
omise du relevé (« modèle véhicule si dans les fichiers »).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class ModelMatch:
    model: str
    score: float  # nombre moyen de bons appariements ORB
    reference_file: str


class VehicleDatabase:
    """Base locale d'images de référence, un dossier par modèle."""

    def __init__(self, directory: str | Path, min_score: float = 18.0) -> None:
        self.directory = Path(directory)
        self.min_score = min_score
        self._orb = cv2.ORB_create(nfeatures=800)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        # [(nom_modele, chemin, descripteurs)]
        self._references: list[tuple[str, str, np.ndarray]] = []
        self._load()

    def _load(self) -> None:
        if not self.directory.is_dir():
            return
        for model_dir in sorted(self.directory.iterdir()):
            if not model_dir.is_dir():
                continue
            for image_path in sorted(model_dir.iterdir()):
                if image_path.suffix.lower() not in _IMAGE_EXTS:
                    continue
                image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
                if image is None:
                    continue
                _, desc = self._orb.detectAndCompute(image, None)
                if desc is not None and len(desc) >= 10:
                    self._references.append((model_dir.name, str(image_path), desc))

    @property
    def available(self) -> bool:
        return bool(self._references)

    def match(self, vehicle_crop: np.ndarray) -> Optional[ModelMatch]:
        """Meilleur modèle correspondant, ou None si base vide / score trop bas."""
        if not self.available or vehicle_crop.size == 0:
            return None
        gray = (
            cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
            if vehicle_crop.ndim == 3
            else vehicle_crop
        )
        _, desc = self._orb.detectAndCompute(gray, None)
        if desc is None or len(desc) < 10:
            return None

        best: Optional[ModelMatch] = None
        for model, path, ref_desc in self._references:
            matches = self._matcher.knnMatch(desc, ref_desc, k=2)
            # Test de ratio de Lowe : garde les appariements discriminants.
            good = sum(
                1 for pair in matches if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance
            )
            if best is None or good > best.score:
                best = ModelMatch(model=model, score=float(good), reference_file=path)
        if best is None or best.score < self.min_score:
            return None
        return best
