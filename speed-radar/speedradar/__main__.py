"""Point d'entrée en ligne de commande: `python -m speedradar`."""

from __future__ import annotations

import argparse
import logging

from .config import load_config
from .pipeline import SpeedRadar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="speedradar",
        description=(
            "Radar de vitesse auto-calibrant pour n'importe quelle caméra "
            "(webcam, smartphone, RTSP, fichier vidéo)."
        ),
    )
    parser.add_argument(
        "--source",
        help="Source vidéo: index webcam (0), URL RTSP/HTTP, ou fichier vidéo",
    )
    parser.add_argument("--config", help="Chemin du fichier config.yaml")
    parser.add_argument(
        "--limit", type=float, help="Limite de vitesse contrôlée (km/h)"
    )
    parser.add_argument(
        "--record-all",
        action="store_true",
        help="Enregistrer tous les passages mesurés, pas seulement les excès",
    )
    parser.add_argument(
        "--display", action="store_true", help="Afficher la vidéo annotée en direct"
    )
    parser.add_argument(
        "--max-frames", type=int, help="S'arrêter après N images (tests/démos)"
    )
    parser.add_argument(
        "--verifier-journal",
        metavar="RELEVES.JSONL",
        help="Vérifier l'intégrité (chaînage + signatures) d'un journal scellé, puis quitter",
    )
    parser.add_argument(
        "--autotest",
        action="store_true",
        help="Exécuter l'autotest métrologique, afficher le rapport, puis quitter",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.verifier_journal:
        from .integrity import SealedEventLog

        errors = SealedEventLog(args.verifier_journal).verify()
        if errors:
            for e in errors:
                print(f"ALTÉRATION DÉTECTÉE — {e}")
            return 1
        print("Journal intact : chaînage et signatures valides.")
        return 0

    if args.autotest:
        import json

        from .integrity import run_self_test

        report = run_self_test()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["ok"] else 1

    config = load_config(args.config)
    if args.source is not None:
        config.source = args.source
    if args.limit is not None:
        config.speed_limit_kmh = args.limit
    if args.record_all:
        config.recording.record_all = True

    SpeedRadar(config).run(display=args.display, max_frames=args.max_frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
