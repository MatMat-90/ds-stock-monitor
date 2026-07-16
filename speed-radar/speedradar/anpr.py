"""Lecture de plaque d'immatriculation (ANPR).

La localisation de la plaque utilise des heuristiques de contours OpenCV
(rectangle clair, ratio largeur/hauteur typique). L'OCR s'appuie sur
`easyocr` ou `pytesseract` si l'un des deux est installé ; sinon la lecture
est simplement désactivée (le reste du radar fonctionne normalement).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

# Format français SIV : AA-123-AA. D'autres formats restent acceptés en brut.
_FR_PLATE = re.compile(r"([A-Z]{2})[\s-]?(\d{3})[\s-]?([A-Z]{2})")


def normalize_plate(raw: str) -> Optional[str]:
    """Nettoie un texte OCR et le met au format AA-123-AA si possible."""
    text = re.sub(r"[^A-Z0-9]", "", raw.upper().replace("O", "0"))
    # L'OCR confond souvent 0/O, 1/I, 5/S, 8/B : on tente les deux lectures.
    candidates = [text, text.replace("0", "O")]
    for cand in candidates:
        m = _FR_PLATE.search(cand)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


@dataclass
class PlateResult:
    text: str  # texte normalisé (ou brut si non normalisable)
    confidence: float
    normalized: bool


def find_plate_candidates(vehicle_crop: np.ndarray, max_candidates: int = 5) -> list[np.ndarray]:
    """Régions de l'image du véhicule ressemblant à une plaque."""
    gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 60, 60)
    edges = cv2.Canny(gray, 60, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    scored: list[tuple[float, np.ndarray]] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 40 or h < 10:
            continue
        ratio = w / h
        if not 2.0 <= ratio <= 6.5:  # plaque EU ~ 4.6, tolérance large
            continue
        crop = gray[y : y + h, x : x + w]
        # Les plaques sont claires et contrastées.
        score = float(crop.mean()) + float(crop.std())
        scored.append((score, crop))
    scored.sort(key=lambda s: -s[0])
    return [crop for _, crop in scored[:max_candidates]]


def _ocr_easyocr(image: np.ndarray) -> Optional[tuple[str, float]]:
    try:
        import easyocr
    except ImportError:
        return None
    reader = _ocr_easyocr.__dict__.setdefault(
        "_reader", easyocr.Reader(["fr", "en"], gpu=False, verbose=False)
    )
    results = reader.readtext(image, detail=1)
    if not results:
        return None
    _, text, conf = max(results, key=lambda r: r[2])
    return text, float(conf)


def _ocr_tesseract(image: np.ndarray) -> Optional[tuple[str, float]]:
    try:
        import pytesseract
    except ImportError:
        return None
    config = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
    text = pytesseract.image_to_string(image, config=config).strip()
    return (text, 0.5) if text else None


def read_plate(vehicle_crop: np.ndarray) -> Optional[PlateResult]:
    """Tente de lire la plaque sur l'image d'un véhicule.

    Retourne None si aucune plaque lisible ou aucun moteur OCR installé.
    """
    if vehicle_crop.size == 0:
        return None
    best: Optional[PlateResult] = None
    for candidate in find_plate_candidates(vehicle_crop) or [
        cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
    ]:
        # Agrandir aide beaucoup les OCR sur les petites plaques.
        scaled = cv2.resize(candidate, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        result = _ocr_easyocr(scaled) or _ocr_tesseract(scaled)
        if result is None:
            continue
        raw, conf = result
        normalized = normalize_plate(raw)
        plate = PlateResult(
            text=normalized or raw.strip(),
            confidence=conf + (0.25 if normalized else 0.0),
            normalized=normalized is not None,
        )
        if best is None or plate.confidence > best.confidence:
            best = plate
    return best
