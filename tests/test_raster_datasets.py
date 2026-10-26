import math

import numpy as np
import pytest

from volscan.datasets import load_fdsn_text
from volscan.grid import Grid
from volscan.raster import brier, compare, rasterize_rings


def grid10():
    return Grid(elev=np.zeros((10, 10)), west=0.0, north=100.0, step=10.0)


def square(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]], float)


def test_square_covers_exactly_the_cell_centres_inside():
    m = rasterize_rings(grid10(), [square(20, 20, 60, 50)])
    # centres at 5, 15, ...; x in (20,60) -> cols 2..5 ; y in (20,50) -> rows 5..7
    assert m.sum() == 4 * 3
    assert m[5:8, 2:6].all()


def test_hole_is_left_empty():
    m = rasterize_rings(grid10(), [square(0, 0, 100, 100), square(30, 30, 70, 70)])
    assert not m[3:7, 3:7].any()
    assert m.sum() == 100 - 16


def test_two_parts_are_both_filled():
    m = rasterize_rings(grid10(), [square(0, 0, 20, 20), square(80, 80, 100, 100)])
    assert m.sum() == 8


def test_compare_metrics():
    pred = np.array([[1, 1, 0, 0]], bool)
    obs = np.array([[0, 1, 1, 0]], bool)
    c = compare(pred, obs)
    assert c["iou"] == pytest.approx(1 / 3)
    assert c["hit_rate"] == 0.5 and c["false_alarm_ratio"] == 0.5


def test_compare_with_nothing_is_nan_not_zero():
    c = compare(np.zeros((2, 2), bool), np.zeros((2, 2), bool))
    assert math.isnan(c["iou"])


def test_brier_perfect_and_worst():
    obs = np.array([1, 0, 1], bool)
    assert brier(obs.astype(float), obs) == 0
    assert brier(1 - obs.astype(float), obs) == 1


def test_fdsn_text_parsing_keeps_missing_as_none(tmp_path):
    p = tmp_path / "q.txt"
    p.write_text("#EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|ContributorID|MagType|Magnitude|MagAuthor|EventLocationName\n"
                 "b|2021-09-12T23:58:12.0Z|28.57|-17.85||MDD|X|MDD|1|ml||MDD|CANARY\n"
                 "a|2021-09-11T03:18:42.7Z|28.57|-17.87|11.0|MDD|X|MDD|2|ml|1.5|MDD|CANARY\n")
    qs = load_fdsn_text(p)
    assert [q.event_id for q in qs] == ["a", "b"]           # sorted by time
    assert qs[1].depth_km is None and qs[1].mag is None
    assert qs[0].mag == 1.5


def test_overlapping_parts_do_not_cancel(monkeypatch):
    import volscan.raster as R
    monkeypatch.setattr(R, "_rings_xy", lambda polys: [np.asarray(r, float) for p in polys for r in p])
    a = square(0, 0, 60, 60).tolist()
    b = square(30, 30, 100, 100).tolist()
    m = R.rasterize_lonlat(grid10(), [[a], [b]])
    assert m[5, 4]        # centre (45, 45) lies in both parts
