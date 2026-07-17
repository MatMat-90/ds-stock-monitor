import os

import pytest

from speedradar import sources


def test_is_skyline_page():
    assert sources.is_skyline_page(
        "https://www.skylinewebcams.com/fr/webcam/italia/lombardia/milano/x.html"
    )
    assert not sources.is_skyline_page("0")
    assert not sources.is_skyline_page("rtsp://cam/stream")
    assert not sources.is_skyline_page("route.mp4")


def test_resolve_skyline_parses_token(monkeypatch):
    # resolve_skyline fait `import requests` en interne : on patche requests.get.
    class FakeResp:
        text = "<html>...isMobile},source:'livee.m3u8?a=abc123xyz',persistConfig:true..."

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp())
    url = sources.resolve_skyline("https://www.skylinewebcams.com/fr/webcam/x.html")
    assert url == "https://hd-auth.skylinewebcams.com/live.m3u8?a=abc123xyz"


def test_resolve_skyline_premium_raises(monkeypatch):
    class FakeResp:
        text = "<html>... this is a PREMIUM webcam ...</html>"

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="premium"):
        sources.resolve_skyline("https://www.skylinewebcams.com/fr/webcam/x.html")


def test_resolve_source_passthrough():
    assert sources.resolve_source("0") == "0"
    assert sources.resolve_source("route.mp4") == "route.mp4"
    assert sources.resolve_source("rtsp://cam/stream") == "rtsp://cam/stream"


def test_resolve_source_sets_referer_for_skyline_hls():
    os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
    out = sources.resolve_source(
        "https://hd-auth.skylinewebcams.com/live.m3u8?a=tok"
    )
    assert out.endswith("live.m3u8?a=tok")
    assert "referer" in os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS", "")
