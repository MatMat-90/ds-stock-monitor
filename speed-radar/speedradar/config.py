"""Chargement et validation de la configuration (fichier YAML + valeurs par défaut)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CalibrationConfig:
    # Longueur moyenne d'un véhicule léger (mètres), utilisée comme référence
    # statistique pour l'auto-calibration.
    mean_vehicle_length_m: float = 4.4
    # Nombre minimal d'observations avant de considérer la calibration fiable.
    min_samples: int = 30
    # Nombre de bandes horizontales de l'image (l'échelle m/px varie avec la
    # profondeur de la scène, donc avec la position verticale).
    bands: int = 8
    # Correspondances image -> sol fournies manuellement (4 points ou plus),
    # pour une calibration précise par homographie. Optionnel.
    # Format: [[px_x, px_y, sol_x_m, sol_y_m], ...]
    ground_points: Optional[list] = None


@dataclass
class DetectionConfig:
    # Aire minimale (px²) d'un contour pour être considéré comme véhicule.
    min_area: int = 1500
    # Aire maximale relative (fraction de l'image) pour écarter les artefacts.
    max_area_ratio: float = 0.5
    # Utiliser YOLO si le paquet `ultralytics` est installé (sinon soustraction
    # de fond OpenCV, qui fonctionne partout).
    prefer_yolo: bool = True
    yolo_model: str = "yolov8n.pt"


@dataclass
class TrackingConfig:
    # Distance maximale (px) entre deux positions successives d'un même objet.
    max_distance: float = 120.0
    # Nombre d'images sans détection avant de clore une piste.
    max_missed: int = 10
    # Nombre minimal de points d'une piste pour estimer une vitesse.
    min_track_points: int = 8


@dataclass
class RecordingConfig:
    # Durées (secondes) conservées avant et après l'événement.
    pre_seconds: float = 4.0
    post_seconds: float = 3.0
    # Dossier de sortie des extraits, instantanés et relevés.
    output_dir: str = "captures"
    # Enregistrer tous les véhicules mesurés (true) ou seulement les excès (false).
    record_all: bool = False


@dataclass
class RadarConfig:
    # Limite de vitesse contrôlée (km/h).
    speed_limit_kmh: float = 50.0
    # Tolérance appliquée avant de déclencher (km/h), comme un vrai radar.
    tolerance_kmh: float = 5.0
    # Source vidéo: index webcam (0), URL RTSP/HTTP, ou chemin de fichier.
    source: str = "0"
    # Images par seconde supposées si la source ne les fournit pas.
    fallback_fps: float = 25.0
    # Dossier des images de référence pour l'identification du modèle.
    vehicle_db_dir: str = "data/vehicles"
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)


def load_config(path: str | Path | None) -> RadarConfig:
    """Charge un YAML de configuration; toute clé absente garde sa valeur par défaut."""
    cfg = RadarConfig()
    if path is None:
        return cfg
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    for section_name in ("calibration", "detection", "tracking", "recording"):
        section = data.pop(section_name, {}) or {}
        target = getattr(cfg, section_name)
        for key, value in section.items():
            if not hasattr(target, key):
                raise ValueError(f"Clé inconnue: {section_name}.{key}")
            setattr(target, key, value)
    for key, value in data.items():
        if not hasattr(cfg, key):
            raise ValueError(f"Clé inconnue: {key}")
        setattr(cfg, key, value)
    return cfg
