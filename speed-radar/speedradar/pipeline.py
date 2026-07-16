"""Orchestration complète du radar : capture -> détection -> suivi ->
auto-calibration -> vitesse -> enregistrement de l'extrait utile -> relevé."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import numpy as np

from .anpr import read_plate
from .calibration import AutoCalibrator, PlanarCalibration
from .config import RadarConfig
from .detection import build_detector
from .events import EventLog, SpeedEvent
from .recorder import EventRecorder
from .ring_buffer import FrameRingBuffer
from .speed import SpeedEstimate, estimate_speed
from .tracking import CentroidTracker, Track
from .vehicle_db import VehicleDatabase

log = logging.getLogger("speedradar")


def open_source(source: str, fallback_fps: float) -> tuple[cv2.VideoCapture, float, bool]:
    """Ouvre une source vidéo quelconque.

    - "0", "1"...            -> webcam locale ;
    - "rtsp://...", "http://..." -> caméra IP / surveillance / app smartphone ;
    - chemin de fichier      -> rejeu d'une vidéo.

    Retourne (capture, fps, is_live).
    """
    is_file = Path(source).exists()
    cap = cv2.VideoCapture(int(source) if source.isdigit() else source)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la source vidéo: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 1 or fps > 240:
        fps = fallback_fps
    return cap, float(fps), not is_file


class SpeedRadar:
    """Boucle principale du radar."""

    def __init__(self, config: RadarConfig) -> None:
        self.cfg = config
        self.detector = build_detector(
            prefer_yolo=config.detection.prefer_yolo,
            yolo_model=config.detection.yolo_model,
            min_area=config.detection.min_area,
            max_area_ratio=config.detection.max_area_ratio,
        )
        self.tracker = CentroidTracker(
            max_distance=config.tracking.max_distance,
            max_missed=config.tracking.max_missed,
        )
        self.planar: PlanarCalibration | None = None
        if config.calibration.ground_points:
            self.planar = PlanarCalibration.from_ground_points(
                config.calibration.ground_points
            )
            log.info("Calibration par homographie sol (points fournis)")
        self.calibrator: AutoCalibrator | None = None  # créé à la 1re image
        self.vehicle_db = VehicleDatabase(config.vehicle_db_dir)
        self.output_dir = Path(config.recording.output_dir)
        self.event_log = EventLog(self.output_dir / "releves.jsonl")
        self._recorder: EventRecorder | None = None
        self._pending_event: SpeedEvent | None = None
        self._recorded_tracks: set[int] = set()

    # ------------------------------------------------------------------
    def run(self, display: bool = False, max_frames: int | None = None) -> None:
        cap, fps, is_live = open_source(self.cfg.source, self.cfg.fallback_fps)
        ring = FrameRingBuffer(self.cfg.recording.pre_seconds, fps)
        frame_idx = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                t = time.monotonic() if is_live else frame_idx / fps
                self.process_frame(t, frame, ring, fps, display=display)
                frame_idx += 1
                if max_frames is not None and frame_idx >= max_frames:
                    break
        finally:
            cap.release()
            if display:
                cv2.destroyAllWindows()
        log.info(
            "Fin de flux. Calibration: %s",
            self.calibrator.summary() if self.calibrator else "homographie",
        )

    # ------------------------------------------------------------------
    def process_frame(
        self,
        t: float,
        frame: np.ndarray,
        ring: FrameRingBuffer,
        fps: float,
        display: bool = False,
    ) -> None:
        if self.calibrator is None:
            self.calibrator = AutoCalibrator(
                frame_height=frame.shape[0],
                mean_vehicle_length_m=self.cfg.calibration.mean_vehicle_length_m,
                bands=self.cfg.calibration.bands,
                min_samples=self.cfg.calibration.min_samples,
            )

        ring.append(t, frame)
        detections = self.detector.detect(frame)
        active, finished = self.tracker.update(t, detections)

        for track in active:
            self._feed_calibrator(track)
            self._maybe_trigger(t, track, ring, fps, frame)

        for track in finished:
            if self._recorder is not None and track.track_id in self._recorded_tracks:
                self._recorder.mark_event_end(t)

        if self._recorder is not None:
            self._recorder.add(t, frame)
            if self._recorder.post_roll_done:
                self._finalize_event()

        if display:
            self._draw_overlay(frame, active)
            cv2.imshow("SpeedRadar", frame)
            cv2.waitKey(1)

    # ------------------------------------------------------------------
    def _feed_calibrator(self, track: Track) -> None:
        """Chaque piste en mouvement net alimente l'auto-calibration."""
        if len(track.points) < 3:
            return
        dx, dy = track.motion_vector()
        if (dx * dx + dy * dy) ** 0.5 < 30:  # objet quasi immobile : inutile
            return
        self.calibrator.observe(track.last.bbox, (dx, dy))

    def _current_speed(self, track: Track) -> SpeedEstimate | None:
        return estimate_speed(
            track,
            calibrator=self.calibrator,
            planar=self.planar,
            min_points=self.cfg.tracking.min_track_points,
        )

    def _maybe_trigger(
        self,
        t: float,
        track: Track,
        ring: FrameRingBuffer,
        fps: float,
        frame: np.ndarray,
    ) -> None:
        if track.track_id in self._recorded_tracks or self._recorder is not None:
            return
        est = self._current_speed(track)
        if est is None or est.quality < 0.7:
            return
        threshold = self.cfg.speed_limit_kmh + self.cfg.tolerance_kmh
        if not self.cfg.recording.record_all and est.kmh <= threshold:
            return

        event = SpeedEvent.create(
            speed_kmh=est.kmh,
            speed_limit_kmh=self.cfg.speed_limit_kmh,
            tolerance_kmh=self.cfg.tolerance_kmh,
            measure_quality=est.quality,
            distance_m=est.distance_m,
            duration_s=est.duration_s,
        )
        event.calibration = (
            {"mode": "homographie"}
            if self.planar
            else {"mode": "auto", **self.calibrator.summary()}
        )
        log.info(
            "Déclenchement piste %d: %.1f km/h (limite %.0f+%.0f)",
            track.track_id,
            est.kmh,
            self.cfg.speed_limit_kmh,
            self.cfg.tolerance_kmh,
        )

        # Instantané + identification sur l'image la plus récente du véhicule.
        crop = self._crop_vehicle(frame, track)
        snapshot_path = self.output_dir / f"{event.event_id}_vehicule.jpg"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(snapshot_path), crop)
        event.snapshot_path = str(snapshot_path)

        plate = read_plate(crop)
        if plate is not None:
            event.plate = plate.text
            event.plate_confidence = round(plate.confidence, 2)

        model = self.vehicle_db.match(crop)
        if model is not None:
            event.vehicle_model = model.model
            event.vehicle_model_score = model.score

        recorder = EventRecorder(fps, post_seconds=self.cfg.recording.post_seconds)
        recorder.start(ring)
        self._recorder = recorder
        self._pending_event = event
        self._recorded_tracks.add(track.track_id)

    def _finalize_event(self) -> None:
        event, recorder = self._pending_event, self._recorder
        self._pending_event, self._recorder = None, None
        clip_path = self.output_dir / f"{event.event_id}_extrait.mp4"
        event.clip_path = str(recorder.save(clip_path))
        self.event_log.append(event)
        log.info("Relevé enregistré: %s (%s)", event.event_id, event.clip_path)

    # ------------------------------------------------------------------
    @staticmethod
    def _crop_vehicle(frame: np.ndarray, track: Track, margin: float = 0.15) -> np.ndarray:
        x, y, w, h = track.last.bbox
        mx, my = w * margin, h * margin
        x0 = max(0, int(x - mx))
        y0 = max(0, int(y - my))
        x1 = min(frame.shape[1], int(x + w + mx))
        y1 = min(frame.shape[0], int(y + h + my))
        return frame[y0:y1, x0:x1].copy()

    def _draw_overlay(self, frame: np.ndarray, tracks: list[Track]) -> None:
        status = (
            "CALIBRE"
            if self.planar or (self.calibrator and self.calibrator.is_calibrated)
            else f"calibration {self.calibrator.sample_count}/{self.cfg.calibration.min_samples}"
        )
        cv2.putText(
            frame, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
        )
        for track in tracks:
            x, y, w, h = (int(v) for v in track.last.bbox)
            est = self._current_speed(track)
            over = est and est.kmh > self.cfg.speed_limit_kmh + self.cfg.tolerance_kmh
            color = (0, 0, 255) if over else (0, 255, 0)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            label = f"#{track.track_id}" + (f" {est.kmh:.0f} km/h" if est else "")
            cv2.putText(
                frame, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
            )
