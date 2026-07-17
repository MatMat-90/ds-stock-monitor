#!/usr/bin/env bash
# Démo « clé USB » : lance le radar de vitesse sur n'importe quel flux vidéo.
#
# Usage :
#   ./demo.sh                              # webcam locale (index 0)
#   ./demo.sh 0                            # webcam locale
#   ./demo.sh route.mp4                    # fichier vidéo
#   ./demo.sh "rtsp://user:mdp@ip/stream"  # caméra RTSP
#   ./demo.sh "http://192.168.1.30:8080/video"   # smartphone (IP Webcam)
#   ./demo.sh "https://www.skylinewebcams.com/fr/webcam/.../x.html"  # page Skyline
#
# À la première exécution, installe les dépendances dans un environnement
# virtuel local (.venv) — rien n'est installé sur le système.

set -e
cd "$(dirname "$0")"

SOURCE="${1:-0}"
LIMIT="${SPEED_LIMIT:-50}"

if [ ! -d ".venv" ]; then
  echo "[demo] Première exécution : installation des dépendances (une seule fois)…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
  # YOLO facultatif : détection plus précise si l'installation réussit.
  ./.venv/bin/pip install --quiet ultralytics 2>/dev/null || \
    echo "[demo] (ultralytics non installé : bascule sur la soustraction de fond)"
fi

echo "[demo] Lancement du radar sur : $SOURCE  (limite ${LIMIT} km/h)"
echo "[demo] Fenêtre annotée en temps réel — Ctrl-C pour arrêter."
exec ./.venv/bin/python -m speedradar --source "$SOURCE" --limit "$LIMIT" --display "${@:2}"
