import json

from speedradar.anpr import normalize_plate
from speedradar.events import EventLog, SpeedEvent


def test_normalize_plate_standard():
    assert normalize_plate("AB-123-CD") == "AB-123-CD"
    assert normalize_plate("ab 123 cd") == "AB-123-CD"
    assert normalize_plate("AB123CD") == "AB-123-CD"


def test_normalize_plate_with_ocr_noise():
    assert normalize_plate("[AB-123-CD]") == "AB-123-CD"
    assert normalize_plate("FR AB123CD") == "AB-123-CD"


def test_normalize_plate_rejects_garbage():
    assert normalize_plate("HELLO") is None
    assert normalize_plate("12345") is None
    assert normalize_plate("") is None


def test_event_violation_flag():
    over = SpeedEvent.create(
        speed_kmh=63.2, speed_limit_kmh=50, tolerance_kmh=5,
        measure_quality=0.98, distance_m=22.0, duration_s=1.3,
    )
    assert over.is_violation
    under = SpeedEvent.create(
        speed_kmh=54.0, speed_limit_kmh=50, tolerance_kmh=5,
        measure_quality=0.98, distance_m=20.0, duration_s=1.4,
    )
    assert not under.is_violation  # dans la tolérance


def test_event_log_roundtrip(tmp_path):
    log = EventLog(tmp_path / "releves.jsonl")
    event = SpeedEvent.create(
        speed_kmh=72.4, speed_limit_kmh=50, tolerance_kmh=5,
        measure_quality=0.95, distance_m=30.0, duration_s=1.5,
    )
    event.plate = "AB-123-CD"
    event.vehicle_model = "renault_clio"
    log.append(event)

    loaded = log.read_all()
    assert len(loaded) == 1
    assert loaded[0].speed_kmh == 72.4
    assert loaded[0].plate == "AB-123-CD"
    assert loaded[0].is_violation

    # Le JSONL reste lisible par n'importe quel outil.
    line = (tmp_path / "releves.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["vehicle_model"] == "renault_clio"
