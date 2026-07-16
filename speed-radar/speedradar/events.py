"""Relevés d'infraction : structure, sérialisation et journal JSONL."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class SpeedEvent:
    """Relevé complet d'un passage mesuré."""

    event_id: str
    timestamp_utc: str
    speed_kmh: float
    speed_limit_kmh: float
    tolerance_kmh: float
    is_violation: bool
    measure_quality: float  # R² de la régression de vitesse (0-1)
    distance_m: float
    duration_s: float
    plate: Optional[str] = None
    plate_confidence: Optional[float] = None
    vehicle_model: Optional[str] = None
    vehicle_model_score: Optional[float] = None
    clip_path: Optional[str] = None
    snapshot_path: Optional[str] = None
    calibration: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        speed_kmh: float,
        speed_limit_kmh: float,
        tolerance_kmh: float,
        measure_quality: float,
        distance_m: float,
        duration_s: float,
    ) -> "SpeedEvent":
        now = datetime.now(timezone.utc)
        return cls(
            event_id=now.strftime("%Y%m%d-%H%M%S-%f"),
            timestamp_utc=now.isoformat(),
            speed_kmh=round(speed_kmh, 1),
            speed_limit_kmh=speed_limit_kmh,
            tolerance_kmh=tolerance_kmh,
            is_violation=speed_kmh > speed_limit_kmh + tolerance_kmh,
            measure_quality=round(measure_quality, 3),
            distance_m=round(distance_m, 1),
            duration_s=round(duration_s, 2),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class EventLog:
    """Journal des relevés, une ligne JSON par événement (JSONL)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: SpeedEvent) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

    def read_all(self) -> list[SpeedEvent]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(SpeedEvent(**json.loads(line)))
        return events
