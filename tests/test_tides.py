import datetime as dt

import numpy as np
import pytest

from volscan.tides import decluster, lunar_elongation, schuster, tidal_phase, tidal_potential


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def ang_diff(a, b):
    return abs((a - b + 180) % 360 - 180)


@pytest.mark.parametrize("when,expected", [
    ("2021-09-20T23:55:00Z", 180.0),   # full moon (USNO)
    ("2021-10-06T11:05:00Z", 0.0),     # new moon
    ("2011-10-12T02:06:00Z", 180.0),   # full moon two days after the El Hierro eruption began
])
def test_lunar_elongation_matches_published_phases(when, expected):
    assert ang_diff(float(lunar_elongation(ts(when))), expected) < 1.5


def test_tidal_potential_is_semidiurnal_lunar():
    t = np.arange(ts("2021-09-01T00:00:00Z"), ts("2021-10-01T00:00:00Z"), 300.0)
    w = tidal_potential(t, 28.6, -17.9)
    peaks = np.flatnonzero((w[1:-1] > w[:-2]) & (w[1:-1] >= w[2:])) + 1
    gaps_h = np.diff(t[peaks]) / 3600
    assert np.mean(gaps_h) == pytest.approx(12.42, abs=0.15)


def test_phase_is_zero_at_a_maximum_and_in_range():
    t = np.arange(ts("2021-09-10T00:00:00Z"), ts("2021-09-12T00:00:00Z"), 60.0)
    w = tidal_potential(t, 28.6, -17.9)
    k = int(np.argmax(w[: 13 * 60]))
    ph = tidal_phase([t[k] + 1, t[k] + 6.2 * 3600], 28.6, -17.9)
    assert ph[0] < 2 or ph[0] > 358
    assert 160 < ph[1] < 200          # about half a cycle later
    rand = tidal_phase(np.random.default_rng(0).uniform(t[0], t[-1], 200), 28.6, -17.9)
    assert np.nanmin(rand) >= 0 and np.nanmax(rand) < 360


def test_schuster_uniform_is_not_significant_and_clustered_is():
    rng = np.random.default_rng(1)
    assert schuster(rng.uniform(0, 360, 2000))["p"] > 0.01
    s = schuster(rng.normal(90, 20, 300) % 360)
    assert s["p"] < 1e-10 and ang_diff(s["mean_phase_deg"], 90) < 5


def test_schuster_ignores_nan_and_handles_empty():
    assert schuster([np.nan, 10, 10])["n"] == 2
    assert np.isnan(schuster([])["p"])


def test_decluster_keeps_largest_per_window():
    t = np.array([0, 100, 200, 7 * 3600, 7 * 3600 + 5], float)
    m = np.array([1.0, 3.0, 2.0, np.nan, 0.5])
    keep = decluster(t, m, hours=6)
    assert keep.tolist() == [False, True, False, False, True]
