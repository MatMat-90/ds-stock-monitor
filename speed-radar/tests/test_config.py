import pytest

from speedradar.config import RadarConfig, load_config


def test_defaults():
    cfg = load_config(None)
    assert isinstance(cfg, RadarConfig)
    assert cfg.speed_limit_kmh == 50.0
    assert cfg.calibration.mean_vehicle_length_m == 4.4


def test_partial_yaml_overrides(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "speed_limit_kmh: 30\n"
        "source: rtsp://cam.local/stream\n"
        "recording:\n  record_all: true\n  pre_seconds: 6\n"
        "calibration:\n  min_samples: 50\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.speed_limit_kmh == 30
    assert cfg.source == "rtsp://cam.local/stream"
    assert cfg.recording.record_all is True
    assert cfg.recording.pre_seconds == 6
    assert cfg.calibration.min_samples == 50
    # Les valeurs non mentionnées gardent leurs défauts.
    assert cfg.tolerance_kmh == 5.0
    assert cfg.recording.post_seconds == 3.0


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("vitesse_max: 90\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)
