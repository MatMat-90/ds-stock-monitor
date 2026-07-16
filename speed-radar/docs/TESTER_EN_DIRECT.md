# Tester SpeedRadar en direct sur du vrai trafic

Ce guide donne des sources vidéo **légitimes** pour tester le radar en
conditions réelles. Le point important : le logiciel accepte n'importe quelle
source, mais **la source doit être une caméra dont vous avez le droit d'usage**.

> ⚠️ N'utilisez pas de caméras « ouvertes » trouvées sur Internet (Insecam,
> Shodan…). Ce sont presque toujours des caméras privées non sécurisées : y
> accéder est un accès non autorisé (art. 323-1 du code pénal) et en lire les
> plaques est un traitement de données personnelles illicite (RGPD/CNIL).
> Voir [HOMOLOGATION.md](HOMOLOGATION.md) pour le cadre légal complet.

## Le plus rapide : votre smartphone (2 minutes)

C'est la meilleure façon de tester en direct sur une vraie rue.

1. **Android** — installez *IP Webcam* ; **iOS** — *Larix Broadcaster* (RTSP)
   ou toute app qui expose un flux MJPEG/RTSP.
2. Posez le téléphone sur un support stable (fenêtre, balcon, trépied),
   cadrez la chaussée de façon à voir les véhicules se déplacer sur une
   bonne longueur (une vue de 3/4 est idéale, pas frontale).
3. Lancez le serveur de l'app : elle affiche une URL, par exemple
   `http://192.168.1.30:8080/video`.
4. Sur un ordinateur du même réseau Wi-Fi :

```bash
cd speed-radar
python -m speedradar --source http://192.168.1.30:8080/video --limit 50 --display
```

La fenêtre affiche les détections, la vitesse estimée par véhicule, et l'état
de calibration (« calibration N/30 » puis « CALIBRE »). Laissez passer
quelques dizaines de véhicules : l'auto-calibration converge, puis les
mesures et enregistrements démarrent.

## Webcam USB

Posée derrière une vitre donnant sur la rue :

```bash
python -m speedradar --source 0 --limit 50 --display
```

## Vos propres caméras (surveillance / domotique)

Si vous êtes responsable de la caméra, utilisez son URL RTSP :

```bash
python -m speedradar --source "rtsp://utilisateur:motdepasse@192.168.1.20/stream1" --limit 50
```

## Flux publics officiels

Certaines collectivités et offices de tourisme publient des webcams **dont les
conditions d'utilisation autorisent la consultation/réutilisation**. Vérifiez
toujours les CGU de la source avant de l'utiliser, et gardez à l'esprit que
lire des plaques dessus reste soumis au RGPD. Beaucoup de ces flux sont des
images JPEG rafraîchies périodiquement (pas de la vidéo) et ne conviennent pas
à la mesure de vitesse, qui a besoin d'une cadence régulière.

## Vidéos enregistrées (pour mesurer la précision au calme)

Pour évaluer la précision sans contrainte de temps réel, rejouez un fichier :

```bash
python -m speedradar --source trafic.mp4 --limit 50 --display --record-all
```

Utilisez des vidéos de trafic **librement réutilisables** (jeux de données de
vision par ordinateur sous licence ouverte, vos propres enregistrements). Avec
une vidéo où une vitesse de référence est connue (GPS d'un véhicule sonde, ou
distance/temps mesurés), vous pouvez quantifier l'erreur du radar.

## Régler pour de meilleurs résultats

| Symptôme | Réglage (`config.yaml` ou options) |
|---|---|
| Reste bloqué en « calibration N/30 » | Baisser `calibration.min_samples` ; s'assurer que les véhicules traversent une bonne portion de l'image |
| Véhicules non détectés | Baisser `detection.min_area` ; installer `ultralytics` pour la détection YOLO |
| Détections parasites (ombres, feuillage) | Monter `detection.min_area` ; stabiliser la caméra |
| Vitesses fantaisistes | Fournir une calibration par homographie (`calibration.ground_points`) mesurée sur place — bien plus précise que l'auto-calibration statistique |
| Trop / pas assez d'enregistrements | Ajuster `speed_limit_kmh` et `tolerance_kmh`, ou `--record-all` pour tout garder |

## Retour d'un test réel (footage libre de droits)

Le pipeline a été testé sur des vidéos de trafic librement réutilisables
(Wikimedia Commons : autoroute E18 à Lysaker, Norvège — domaine public ;
Ayalon Freeway, Tel Aviv — CC BY-SA). Enseignements concrets :

- **Détection** : avec la soustraction de fond seule, une scène réelle
  complexe (bâtiments, arbres, léger tremblement caméra) génère beaucoup de
  fausses détections. Avec **YOLO**, seules les véhicules sont détectés — la
  différence est spectaculaire. Installez YOLO pour tout usage sérieux.
- **Suivi** : robuste, un identifiant stable par véhicule.
- **Vitesse** : l'auto-calibration statistique donne le bon ordre de grandeur
  mais reste imprécise sur une **vue oblique** (la perspective déforme
  l'échelle m/px, et la longueur apparente d'un véhicule dépend de l'angle).
  Sur une même autoroute, les estimations peuvent varier du simple au double.
  **Pour des chiffres fiables, fournissez une calibration par homographie**
  (`calibration.ground_points`) : 4 points mesurés sur la chaussée suffisent à
  corriger la perspective.

### Poids YOLO

`ultralytics` télécharge `yolov8n.pt` automatiquement au premier lancement. Si
votre réseau bloque l'asset GitHub, récupérez-le depuis le miroir Hugging Face
et placez-le dans le dossier courant :

```bash
curl -L -o yolov8n.pt https://huggingface.co/Ultralytics/YOLOv8/resolve/main/yolov8n.pt
```

## Vérifier après une session de test

```bash
# Intégrité du journal des relevés
python -m speedradar --verifier-journal captures/releves.jsonl

# Les extraits et instantanés sont dans captures/
ls -l captures/
```
