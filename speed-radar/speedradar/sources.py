"""Résolution de sources vidéo « intelligentes ».

Permet de passer directement à `--source` :
- une URL de **page** SkylineWebcams (ex. .../webcam/.../piazza-san-babila.html) :
  le flux HLS courant est résolu automatiquement, et l'en-tête Referer requis
  est configuré pour OpenCV/ffmpeg ;
- tout le reste (index webcam, URL RTSP/HTTP directe, fichier) est renvoyé tel quel.
"""

from __future__ import annotations

import os
import re

_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
_SKYLINE_HOST = "skylinewebcams.com"
_SKYLINE_SOURCE_RE = re.compile(r"source:'(livee\.m3u8\?a=[a-z0-9]+)'")


def is_skyline_page(source: str) -> bool:
    return _SKYLINE_HOST in source and source.rstrip("/").endswith(".html")


def resolve_skyline(page_url: str) -> str:
    """Extrait l'URL HLS courante d'une page webcam SkylineWebcams.

    La page publie `source:'livee.m3u8?a=<token>'` ; le lecteur construit
    `https://hd-auth.skylinewebcams.com/live.m3u8?a=<token>`. Le token est
    régénéré à chaque chargement (à ré-résoudre pour chaque session).
    """
    import requests  # dépendance déjà présente dans le projet

    html = requests.get(page_url, headers={"User-Agent": _UA}, timeout=30).text
    m = _SKYLINE_SOURCE_RE.search(html)
    if not m:
        if "premium" in html.lower():
            raise RuntimeError(
                "caméra SkylineWebcams premium (payante) : flux non accessible librement"
            )
        raise RuntimeError("flux SkylineWebcams introuvable sur la page")
    return "https://hd-auth.skylinewebcams.com/" + m.group(1).replace("livee.", "live.")


def set_ffmpeg_referer(referer: str) -> None:
    """Configure le Referer (et l'UA) pour le backend ffmpeg d'OpenCV.

    Nécessaire pour les CDN qui refusent le hotlinking sans Referer (Skyline).
    """
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"referer;{referer}|user_agent;{_UA}"
    )


def resolve_source(source: str) -> str:
    """Transforme une source « intelligente » en source lisible par OpenCV.

    Effet de bord : configure le Referer ffmpeg si la source l'exige.
    """
    if is_skyline_page(source):
        url = resolve_skyline(source)
        set_ffmpeg_referer("https://www.skylinewebcams.com/")
        return url
    if _SKYLINE_HOST in source and ".m3u8" in source:
        set_ffmpeg_referer("https://www.skylinewebcams.com/")
    return source
