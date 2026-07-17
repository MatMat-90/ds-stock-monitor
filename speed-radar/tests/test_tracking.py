from speedradar.tracking import CentroidTracker


def make_bbox(cx, cy, w=80, h=40):
    return (cx - w / 2, cy - h / 2, w, h)


def test_single_object_keeps_same_track_id():
    tracker = CentroidTracker(max_distance=100)
    ids = set()
    for i in range(10):
        active, _ = tracker.update(i * 0.04, [make_bbox(100 + i * 20, 200)])
        assert len(active) == 1
        ids.add(active[0].track_id)
    assert ids == {1}
    assert len(tracker.tracks[1].points) == 10


def test_two_objects_tracked_separately():
    tracker = CentroidTracker(max_distance=100)
    for i in range(8):
        active, _ = tracker.update(
            i * 0.04,
            [make_bbox(100 + i * 15, 100), make_bbox(500 - i * 15, 400)],
        )
    assert len(active) == 2
    lengths = sorted(len(t.points) for t in active)
    assert lengths == [8, 8]


def test_track_closed_after_max_missed():
    tracker = CentroidTracker(max_distance=100, max_missed=3)
    tracker.update(0.0, [make_bbox(100, 100)])
    finished_all = []
    for i in range(1, 6):
        _, finished = tracker.update(i * 0.04, [])
        finished_all.extend(finished)
    assert len(finished_all) == 1
    assert finished_all[0].track_id == 1
    assert tracker.tracks == {}


def test_far_detection_creates_new_track():
    tracker = CentroidTracker(max_distance=50)
    tracker.update(0.0, [make_bbox(100, 100)])
    active, _ = tracker.update(0.04, [make_bbox(600, 500)])
    assert {t.track_id for t in active} == {1, 2}


def test_motion_vector_and_ground_point():
    tracker = CentroidTracker(max_distance=200)
    tracker.update(0.0, [make_bbox(100, 100)])
    active, _ = tracker.update(0.04, [make_bbox(180, 100)])
    track = active[0]
    dx, dy = track.motion_vector()
    assert dx == 80 and dy == 0
    gx, gy = track.ground_point
    assert gx == 180 and gy == 120  # bas de la boîte (h=40 -> cy+20)
