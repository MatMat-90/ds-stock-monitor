# SpeedRadar — radar de vitesse auto-calibrant pour n'importe quelle caméra

Transformez **n'importe quelle caméra** — smartphone, caméra de surveillance,
caméra domotique, webcam — en radar de vitesse : la caméra **s'auto-calibre**
en observant la circulation, **mesure la vitesse** des véhicules, et
**capture en continu mais ne sauvegarde que l'utile** (l'extrait vidéo du
passage, un instantané du véhicule, la plaque si lisible et le modèle si
présent dans vos fichiers de référence).

```
┌──────────┐   ┌───────────┐   ┌────────┐   ┌──────────────────┐   ┌─────────┐
│ Capture  │──▶│ Détection │──▶│ Suivi  │──▶│ Auto-calibration │──▶│ Vitesse │
│ continue │   │ véhicules │   │ pistes │   │ m/px ou homogr.  │   │ (km/h)  │
└────┬─────┘   └───────────┘   └────────┘   └──────────────────┘   └────┬────┘
     │ mémoire circulaire (pré-roll)                     excès détecté │
     ▼                                                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Extrait MP4 (avant + pendant + après) · instantané · plaque (OCR)      │
│  modèle du véhicule (base locale) · relevé JSON (captures/releves.jsonl)│
└─────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
cd speed-radar
pip install -r requirements.txt
# Optionnel mais recommandé :
pip install ultralytics   # détection YOLO plus précise
pip install easyocr       # lecture de plaque
```

## Démarrage rapide

```bash
# Webcam locale, limite 50 km/h
python -m speedradar --source 0 --limit 50

# Smartphone (app "IP Webcam" ou équivalente)
python -m speedradar --source http://192.168.1.30:8080/video --limit 30

# Caméra de surveillance / domotique (RTSP)
python -m speedradar --source "rtsp://user:mdp@192.168.1.20/stream" --limit 50

# Rejeu d'un fichier vidéo, avec affichage annoté
python -m speedradar --source route.mp4 --limit 50 --display

# Tout enregistrer (pas seulement les excès)
python -m speedradar --config config.yaml --record-all
```

Les réglages fins (tolérance, pré/post-roll, seuils de détection...) sont dans
[`config.yaml`](config.yaml).

## Comment marche l'auto-calibration ?

Un radar vidéo doit connaître l'échelle de la scène (combien de mètres vaut un
pixel). Deux modes :

1. **Automatique (zéro réglage)** — les véhicules servent d'étalon : la
   longueur moyenne d'un véhicule léger est connue (~4,4 m). En mesurant la
   longueur apparente en pixels de chaque véhicule le long de sa trajectoire,
   le radar accumule des échantillons mètres/pixel, agrégés par bande
   horizontale de l'image (l'échelle varie avec la profondeur) avec une
   médiane robuste. Après ~30 passages, la calibration converge et les
   mesures commencent.

2. **Homographie sol (précision maximale)** — mesurez sur place 4 points au
   sol (coins de marquages routiers, longueur réglementaire des bandes
   blanches...) et renseignez `calibration.ground_points` dans `config.yaml`.
   Le radar projette alors chaque trajectoire sur le plan de la route.

La vitesse est estimée par régression linéaire de la distance parcourue au
sol en fonction du temps, avec un score de qualité (R²) : les mesures
douteuses (< 0,7) ne déclenchent jamais d'enregistrement.

## Capture continue, sauvegarde utile

Le flux est analysé en continu, mais rien n'est écrit sur disque : les
dernières secondes vivent dans une mémoire circulaire. Quand un excès est
détecté, l'extrait sauvegardé contient le **pré-roll** (les secondes qui
précèdent), le passage, et le **post-roll**. Résultat dans `captures/` :

```
captures/
├── 20260716-142530-123456_extrait.mp4    # extrait vidéo du passage
├── 20260716-142530-123456_vehicule.jpg   # instantané du véhicule
└── releves.jsonl                         # un relevé JSON par événement
```

Exemple de relevé :

```json
{
  "event_id": "20260716-142530-123456",
  "timestamp_utc": "2026-07-16T14:25:30+00:00",
  "speed_kmh": 63.2,
  "speed_limit_kmh": 50.0,
  "tolerance_kmh": 5.0,
  "is_violation": true,
  "measure_quality": 0.98,
  "plate": "AB-123-CD",
  "vehicle_model": "renault_clio",
  "clip_path": "captures/20260716-142530-123456_extrait.mp4"
}
```

## Plaque et modèle du véhicule

- **Plaque** : localisation par heuristiques de contours puis OCR
  (`easyocr` ou `pytesseract`, si installés). Le texte est normalisé au
  format français `AA-123-AA` quand c'est possible. Sans moteur OCR, le champ
  est simplement omis.
- **Modèle** : déposez des images de référence dans `data/vehicles/<modele>/`
  (voir [data/vehicles/README.md](data/vehicles/README.md)). Chaque capture
  est comparée à cette base ; le modèle n'apparaît dans le relevé **que s'il
  figure dans vos fichiers**.

## Tests

```bash
cd speed-radar
python -m pytest tests/ -v
```

La suite couvre le suivi, la convergence de l'auto-calibration, l'estimation
de vitesse, la mémoire circulaire, les relevés, et un test d'intégration qui
fait traverser un véhicule synthétique dans tout le pipeline.

## Intégrité métrologique des relevés

Le projet implémente les exigences *logicielles* applicables aux instruments
de mesure réglementés (guide WELMEC 7.2) — voir
[docs/HOMOLOGATION.md](docs/HOMOLOGATION.md) pour la procédure d'homologation
réelle et l'analyse des écarts :

- **autotest bloquant** au démarrage (géométrie, vitesse, enregistrement,
  horloge) : `python -m speedradar --autotest` ;
- **journal scellé** : chaque relevé est chaîné au précédent et signé
  (HMAC-SHA256) — toute modification, suppression ou insertion a posteriori
  est détectable : `python -m speedradar --verifier-journal captures/releves.jsonl` ;
- **empreintes** : chaque relevé embarque le SHA-256 du logiciel et de la
  configuration qui ont produit la mesure.

## ⚠️ Limites et cadre légal

- Ce projet est un outil **pédagogique et indicatif**. Ce n'est **pas un
  cinémomètre homologué** : ses mesures n'ont aucune valeur légale et ne
  peuvent pas servir à verbaliser.
- La précision de l'auto-calibration statistique dépend du trafic observé
  (typiquement ±10-20 %) ; utilisez l'homographie sol pour faire mieux.
- Filmer la voie publique et lire des plaques d'immatriculation est encadré
  (en France : RGPD, CNIL, code de la sécurité intérieure). Utilisez cet
  outil uniquement dans un cadre autorisé (votre propriété privée, études de
  trafic avec accord, données anonymisées) et ne diffusez pas de données
  personnelles (plaques, visages) sans base légale.
