import json

from speedradar.config import RadarConfig
from speedradar.events import SpeedEvent
from speedradar.integrity import (
    SealedEventLog,
    config_fingerprint,
    run_self_test,
    software_fingerprint,
)


def make_event(speed: float = 72.0) -> SpeedEvent:
    return SpeedEvent.create(
        speed_kmh=speed, speed_limit_kmh=50, tolerance_kmh=5,
        measure_quality=0.95, distance_m=30.0, duration_s=1.5,
    )


def test_fingerprints_are_stable_and_distinct():
    assert software_fingerprint() == software_fingerprint()
    cfg_a, cfg_b = RadarConfig(), RadarConfig()
    assert config_fingerprint(cfg_a) == config_fingerprint(cfg_b)
    cfg_b.speed_limit_kmh = 30.0  # changer un paramètre change l'empreinte
    assert config_fingerprint(cfg_a) != config_fingerprint(cfg_b)


def test_sealed_log_roundtrip_and_verify_ok(tmp_path):
    log = SealedEventLog(tmp_path / "releves.jsonl")
    for s in (61.0, 72.0, 95.5):
        log.append(make_event(s))
    assert log.verify() == []
    events = log.read_all()  # lecture standard toujours possible
    assert [e.speed_kmh for e in events] == [61.0, 72.0, 95.5]


def test_sealed_log_detects_modification(tmp_path):
    path = tmp_path / "releves.jsonl"
    log = SealedEventLog(path)
    log.append(make_event(61.0))
    log.append(make_event(72.0))

    # Falsification : on abaisse la vitesse du 2e relevé.
    lines = path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[1])
    data["speed_kmh"] = 49.0
    lines[1] = json.dumps(data, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors = SealedEventLog(path, key_path=log.key_path).verify()
    assert any("modifié" in e for e in errors)


def test_sealed_log_detects_deletion(tmp_path):
    path = tmp_path / "releves.jsonl"
    log = SealedEventLog(path)
    for s in (61.0, 72.0, 95.5):
        log.append(make_event(s))

    # Suppression du 2e relevé.
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    errors = SealedEventLog(path, key_path=log.key_path).verify()
    assert any("chaîne" in e for e in errors)


def test_sealed_log_detects_forgery_without_key(tmp_path):
    """Un relevé forgé sans la clé de scellement est rejeté même si le
    falsificateur recalcule correctement les hashs de chaînage."""
    import hashlib

    path = tmp_path / "releves.jsonl"
    log = SealedEventLog(path)
    log.append(make_event(61.0))

    prev = json.loads(path.read_text().splitlines()[0])["_scellement"]["hash"]
    forged = make_event(49.0)
    payload = forged.to_json()
    h = hashlib.sha256((prev + payload).encode()).hexdigest()
    line = json.dumps(
        {**json.loads(payload), "_scellement": {"prev": prev, "hash": h, "hmac": "0" * 64}},
        ensure_ascii=False,
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    errors = SealedEventLog(path, key_path=log.key_path).verify()
    assert any("HMAC" in e for e in errors)


def test_sealed_log_resumes_chain_across_restarts(tmp_path):
    path = tmp_path / "releves.jsonl"
    SealedEventLog(path).append(make_event(61.0))
    # Nouveau processus : le chaînage doit continuer, pas repartir de zéro.
    SealedEventLog(path).append(make_event(72.0))
    assert SealedEventLog(path).verify() == []


def test_self_test_passes_and_reports_fingerprint():
    report = run_self_test()
    assert report["ok"], report["checks"]
    assert set(report["checks"]) == {"geometrie", "vitesse", "enregistrement", "horloge"}
    assert report["software_fingerprint"] == software_fingerprint()
