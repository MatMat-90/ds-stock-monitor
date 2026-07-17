"""Détection de véhicules.

Deux moteurs, choisis automatiquement :

- **YOLO** (paquet optionnel `ultralytics`) : plus précis, filtre déjà sur
  les classes véhicules (voiture, moto, bus, camion).
- **Soustraction de fond** (OpenCV MOG2) : fonctionne partout sans modèle,
  adaptée aux caméras fixes (surveillance, domotique, smartphone sur trépied).
"""

from __future__ import annotations

from typing import Protocol

import cv2
import numpy as np

BBox = tuple[float, float, float, float]

# Classes COCO considérées comme véhicules par YOLO.
_YOLO_VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


class Detector(Protocol):
    def detect(self, frame: np.ndarray) -> list[BBox]: ...


class BackgroundSubtractionDetector:
    """Détection par soustraction de fond MOG2 + filtrage morphologique."""

    def __init__(self, min_area: int = 1500, max_area_ratio: float = 0.5) -> None:
        self.min_area = min_area
        self.max_area_ratio = max_area_ratio
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=400, varThreshold=32, detectShadows=True
        )
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

    def detect(self, frame: np.ndarray) -> list[BBox]:
        mask = self._subtractor.apply(frame)
        # Les ombres sont marquées 127 par MOG2 : on ne garde que le premier plan.
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel, iterations=2)

        max_area = frame.shape[0] * frame.shape[1] * self.max_area_ratio
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes: list[BBox] = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            boxes.append((float(x), float(y), float(w), float(h)))
        return boxes


class YoloDetector:
    """Détection par YOLO (nécessite `pip install ultralytics`)."""

    def __init__(self, model_name: str = "yolov8n.pt", conf: float = 0.35) -> None:
        from ultralytics import YOLO  # import différé : dépendance optionnelle

        self._model = YOLO(model_name)
        self._conf = conf

    def detect(self, frame: np.ndarray) -> list[BBox]:
        results = self._model.predict(frame, conf=self._conf, verbose=False)
        boxes: list[BBox] = []
        for r in results:
            for box in r.boxes:
                if int(box.cls) not in _YOLO_VEHICLE_CLASSES:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                boxes.append((x1, y1, x2 - x1, y2 - y1))
        return boxes


def build_detector(
    prefer_yolo: bool = True,
    yolo_model: str = "yolov8n.pt",
    min_area: int = 1500,
    max_area_ratio: float = 0.5,
) -> Detector:
    """Retourne le meilleur détecteur disponible sur cette machine."""
    if prefer_yolo:
        try:
            return YoloDetector(yolo_model)
        except Exception:
            # ultralytics absent, poids introuvables, pas de réseau… : on
            # bascule silencieusement sur la soustraction de fond (marche partout).
            pass
    return BackgroundSubtractionDetector(min_area=min_area, max_area_ratio=max_area_ratio)
