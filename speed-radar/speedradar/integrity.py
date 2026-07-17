"""Exigences logicielles d'un instrument de mesure réglementé.

Ce module implémente la partie *logicielle* des exigences applicables aux
cinémomètres (guide WELMEC 7.2 « Software Guide », recommandation OIML R 91) :

- **empreinte logicielle** : identification univoque de la version exacte du
  code de mesure (toute modification change l'empreinte) ;
- **empreinte de configuration** : les paramètres métrologiques utilisés pour
  chaque mesure sont figés et traçables ;
- **journal scellé** : chaque relevé est chaîné au précédent (hash) et signé
  (HMAC-SHA256) — toute suppression, insertion ou modification a posteriori
  est détectable ;
- **autotest** : l'instrument vérifie ses fonctions de mesure au démarrage et
  refuse de mesurer si un test échoue.

⚠️ Ces mécanismes sont *nécessaires* mais pas *suffisants* pour une
homologation : voir docs/HOMOLOGATION.md pour la procédure réelle.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from pathlib import Path

from .config import RadarConfig
from .events import EventLog, SpeedEvent

_GENESIS = "0" * 64


# ----------------------------------------------------------------------
# Empreintes (identification logicielle et configuration)
# ----------------------------------------------------------------------
def software_fingerprint() -> str:
    """SHA-256 de l'ensemble des sources du paquet, dans un ordre canonique.

    Identifie la version exacte du logiciel de mesure : le moindre octet
    modifié dans le code produit une empreinte différente.
    """
    digest = hashlib.sha256()
    package_dir = Path(__file__).parent
    for source in sorted(package_dir.glob("*.py")):
        digest.update(source.name.encode())
        digest.update(source.read_bytes())
    return digest.hexdigest()


def config_fingerprint(config: RadarConfig) -> str:
    """SHA-256 de la configuration métrologique effective (canonisée)."""
    payload = json.dumps(
        dataclasses.asdict(config), sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# Journal scellé (inviolabilité des relevés)
# ----------------------------------------------------------------------
class SealedEventLog(EventLog):
    """Journal de relevés chaîné et signé.

    Chaque ligne contient le relevé plus un bloc ``_scellement`` :
      - ``prev`` : hash du relevé précédent (chaînage — détecte suppression
        et insertion) ;
      - ``hash`` : SHA-256(prev + relevé) ;
      - ``hmac`` : HMAC-SHA256(clé, hash) — détecte la falsification par qui
        ne détient pas la clé de scellement.

    La clé est générée au premier lancement et stockée à côté du journal
    (fichier en lecture seule propriétaire). Dans un vrai instrument, elle
    résiderait dans un composant matériel scellé.
    """

    def __init__(self, path: str | Path, key_path: str | Path | None = None) -> None:
        super().__init__(path)
        self.key_path = Path(key_path) if key_path else self.path.parent / ".cle_scellement"
        self._key = self._load_or_create_key()
        self._prev_hash = self._last_hash()

    def _load_or_create_key(self) -> bytes:
        if self.key_path.exists():
            return bytes.fromhex(self.key_path.read_text().strip())
        key = secrets.token_bytes(32)
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.write_text(key.hex())
        os.chmod(self.key_path, 0o600)
        return key

    def _last_hash(self) -> str:
        if not self.path.exists():
            return _GENESIS
        lines = [l for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            return _GENESIS
        return json.loads(lines[-1])["_scellement"]["hash"]

    @staticmethod
    def _record_hash(prev: str, event_payload: str) -> str:
        return hashlib.sha256((prev + event_payload).encode("utf-8")).hexdigest()

    def append(self, event: SpeedEvent) -> None:
        payload = event.to_json()
        record_hash = self._record_hash(self._prev_hash, payload)
        seal = {
            "prev": self._prev_hash,
            "hash": record_hash,
            "hmac": hmac.new(self._key, record_hash.encode(), hashlib.sha256).hexdigest(),
        }
        line = json.dumps(
            {**json.loads(payload), "_scellement": seal}, ensure_ascii=False
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        self._prev_hash = record_hash

    def verify(self) -> list[str]:
        """Vérifie l'intégrité complète du journal.

        Retourne la liste des anomalies (vide = journal intact).
        """
        errors: list[str] = []
        if not self.path.exists():
            return errors
        prev = _GENESIS
        for i, line in enumerate(
            l for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()
        ):
            try:
                data = json.loads(line)
                seal = data.pop("_scellement")
            except (json.JSONDecodeError, KeyError):
                errors.append(f"ligne {i + 1}: format invalide ou scellement absent")
                continue
            payload = json.dumps(data, ensure_ascii=False)
            expected_hash = self._record_hash(prev, payload)
            if seal.get("prev") != prev:
                errors.append(f"ligne {i + 1}: rupture de chaîne (relevé supprimé ou inséré)")
            if seal.get("hash") != expected_hash:
                errors.append(f"ligne {i + 1}: relevé modifié après scellement")
            expected_hmac = hmac.new(
                self._key, str(seal.get("hash", "")).encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(str(seal.get("hmac", "")), expected_hmac):
                errors.append(f"ligne {i + 1}: signature HMAC invalide")
            prev = seal.get("hash", expected_hash)
        return errors


# ----------------------------------------------------------------------
# Autotest au démarrage
# ----------------------------------------------------------------------
def run_self_test() -> dict:
    """Vérifie les fonctions de mesure avant toute utilisation.

    Un instrument réglementé doit refuser de mesurer si son autotest échoue
    (WELMEC 7.2, exigence de « fault detection »).
    """
    checks: dict[str, bool] = {}

    # 1. La chaîne géométrique : une homographie connue projette correctement.
    try:
        from .calibration import PlanarCalibration

        cal = PlanarCalibration.from_ground_points(
            [[0, 0, 0, 0], [100, 0, 10, 0], [100, 100, 10, 10], [0, 100, 0, 10]]
        )
        gx, gy = cal.to_ground(50, 50)
        checks["geometrie"] = abs(gx - 5.0) < 1e-6 and abs(gy - 5.0) < 1e-6
    except Exception:
        checks["geometrie"] = False

    # 2. La chaîne cinématique : une piste synthétique donne la vitesse attendue.
    try:
        from .speed import estimate_speed
        from .tracking import Track, TrackPoint

        track = Track(track_id=0)
        for i in range(20):  # 10 px/img à 25 i/s, 0,1 m/px -> 90 km/h
            cx = 100.0 + i * 10
            track.points.append(TrackPoint(i / 25.0, cx, 50.0, (cx - 20, 30, 40, 40)))
        est = estimate_speed(track, planar=cal)
        checks["vitesse"] = est is not None and abs(est.kmh - 90.0) < 0.5
    except Exception:
        checks["vitesse"] = False

    # 3. La chaîne d'enregistrement : le codec vidéo écrit réellement un fichier.
    try:
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "autotest.mp4"
            writer = cv2.VideoWriter(
                str(out), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (32, 32)
            )
            ok = writer.isOpened()
            writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
            writer.release()
            checks["enregistrement"] = ok and out.stat().st_size > 0
    except Exception:
        checks["enregistrement"] = False

    # 4. La base de temps est monotone.
    t0 = time.monotonic()
    checks["horloge"] = time.monotonic() >= t0

    return {
        "ok": all(checks.values()),
        "checks": checks,
        "software_fingerprint": software_fingerprint(),
    }
