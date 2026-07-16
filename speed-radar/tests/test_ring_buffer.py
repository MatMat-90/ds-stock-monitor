import numpy as np
import pytest

from speedradar.recorder import EventRecorder
from speedradar.ring_buffer import FrameRingBuffer


def frame(v: int) -> np.ndarray:
    return np.full((8, 8, 3), v, dtype=np.uint8)


def test_ring_buffer_keeps_only_last_seconds():
    buf = FrameRingBuffer(seconds=2.0, fps=10.0)  # 20 images max
    for i in range(50):
        buf.append(i / 10.0, frame(i % 256))
    assert len(buf) == 20
    snap = buf.snapshot()
    assert snap[0].t == pytest.approx(3.0)  # les 20 dernières: t=3.0 à 4.9
    assert snap[-1].t == pytest.approx(4.9)


def test_snapshot_since():
    buf = FrameRingBuffer(seconds=5.0, fps=10.0)
    for i in range(30):
        buf.append(i / 10.0, frame(0))
    recent = buf.snapshot(since=2.0)
    assert all(bf.t >= 2.0 for bf in recent)
    assert len(recent) == 10


def test_invalid_buffer_params():
    with pytest.raises(ValueError):
        FrameRingBuffer(seconds=0, fps=10)
    with pytest.raises(ValueError):
        FrameRingBuffer(seconds=2, fps=0)


def test_recorder_combines_preroll_and_postroll(tmp_path):
    buf = FrameRingBuffer(seconds=1.0, fps=10.0)
    for i in range(10):  # pré-enregistrement: t=0.0..0.9
        buf.append(i / 10.0, frame(i))

    rec = EventRecorder(fps=10.0, post_seconds=0.5)
    rec.start(buf)
    rec.mark_event_end(1.0)
    t = 1.0
    while not rec.post_roll_done:
        rec.add(t, frame(0))
        t += 0.1
    out = rec.save(tmp_path / "clip.mp4")
    assert out.exists()
    assert out.stat().st_size > 0


def test_recorder_without_frames_raises(tmp_path):
    rec = EventRecorder(fps=10.0)
    with pytest.raises(RuntimeError):
        rec.save(tmp_path / "vide.mp4")
