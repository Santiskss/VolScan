import math

import numpy as np
import pytest

from volscan.grid import Grid
from volscan.lava import (LavaParams, LogNormal, forecast, probability_at, trace_path)

STEP = 25.0


def south_plane(rows=60, cols=41, drop_per_row=2.0, sea_rows=0):
    """Terrain sloping down to the south, optionally with sea (NaN) at the bottom."""
    elev = np.tile(((rows - np.arange(rows)) * drop_per_row)[:, None], (1, cols)).astype(float)
    if sea_rows:
        elev[-sea_rows:, :] = np.nan
    return Grid(elev=elev, west=0.0, north=rows * STEP, step=STEP)


def deterministic(**kw):
    base = dict(n_paths=1, dh_m=0.0, max_length_m=LogNormal(1e9), half_width_m=LogNormal(0.0),
                thickness_m=LogNormal(5.0), viscosity_pa_s=LogNormal(1e5), vent_sigma_m=0.0)
    base.update(kw)
    return LavaParams(**base)


def vent_at(g, i, j):
    return [tuple(float(v) for v in g.ij_to_xy(i, j))]


def test_without_noise_lava_runs_straight_downhill():
    g = south_plane()
    cells, steps, drops, reason = trace_path(g, (0, 20), 0.0, 1e9, np.random.default_rng(0))
    assert [c[1] for c in cells] == [20] * len(cells)
    assert [c[0] for c in cells] == list(range(len(cells)))
    assert reason == "edge"


def test_path_stops_at_max_length():
    g = south_plane()
    cells, steps, _, reason = trace_path(g, (0, 20), 0.0, 10 * STEP + 1, np.random.default_rng(0))
    assert reason == "length" and len(cells) == 11 and sum(steps) <= 10 * STEP + 1


def test_path_reaching_sea_is_reported_as_nodata_not_invented():
    g = south_plane(sea_rows=5)
    cells, _, _, reason = trace_path(g, (0, 20), 0.0, 1e9, np.random.default_rng(0))
    assert reason == "nodata"
    assert all(not math.isnan(g.elev[i, j]) for i, j in cells)


def test_pit_stops_the_flow():
    elev = np.full((9, 9), 100.0)
    elev[4, 4] = 50.0                      # a hole
    g = Grid(elev=elev, west=0, north=9 * STEP, step=STEP)
    cells, _, _, reason = trace_path(g, (4, 4), 0.0, 1e9, np.random.default_rng(0))
    assert reason == "pit" and cells == [(4, 4)]


def dammed_plane(dam_height):
    """A 3-cell-wide channel (high walls on both sides) going south, with a dam across row 20."""
    g = south_plane()
    elev = g.elev.copy()
    elev[:, :19] += 1000.0
    elev[:, 22:] += 1000.0
    elev[20, :] += dam_height + 2.0       # +2 compensates the plane's own drop into row 20
    return Grid(elev=elev, west=g.west, north=g.north, step=g.step)


def test_flow_overtops_a_dam_lower_than_its_thickness():
    g = dammed_plane(3.0)
    cells, _, _, reason = trace_path(g, (0, 20), 0.0, 1e9, np.random.default_rng(0), max_climb_m=8.0)
    assert reason == "edge" and max(c[0] for c in cells) == g.shape[0] - 1


def test_flow_is_stopped_by_a_dam_higher_than_its_thickness():
    g = dammed_plane(20.0)
    cells, _, _, reason = trace_path(g, (0, 20), 0.0, 1e9, np.random.default_rng(0), max_climb_m=8.0)
    assert reason == "pit" and max(c[0] for c in cells) < 20


def test_jeffreys_front_time_matches_analytic():
    g = south_plane(drop_per_row=STEP * math.tan(math.radians(10)))
    h, eta = 5.0, 1e5
    fc = forecast(g, vent_at(g, 0, 20), deterministic(thickness_m=LogNormal(h), viscosity_pa_s=LogNormal(eta)))
    v = 2500 * 9.81 * h * h * math.sin(math.radians(10)) / (3 * eta)
    dist = 40 * STEP / math.cos(math.radians(0))       # 40 rows downhill, horizontal distance
    expected_h = dist / v / 3600
    t = fc.arrival_quantile(1.0)[40, 20]
    assert t == pytest.approx(expected_h, rel=1e-6)


def test_flat_ground_does_not_freeze_the_front():
    g = south_plane(drop_per_row=0.01)
    fc = forecast(g, vent_at(g, 0, 20), deterministic())
    t = fc.arrival_quantile(1.0)
    assert np.isfinite(t[30, 20])


def test_probability_is_downhill_only_and_bounded():
    g = south_plane()
    fc = forecast(g, vent_at(g, 10, 20), LavaParams(n_paths=200, max_length_m=LogNormal(800, 0.3),
                                                    half_width_m=LogNormal(50.0), vent_sigma_m=0.0), seed=1)
    p = fc.probability()
    assert p.max() <= 1 + 1e-9 and p.min() >= 0
    assert p[:7, :].max() == 0             # nothing flows uphill beyond the strip width (2 cells)
    assert p[10, 20] == pytest.approx(1.0)  # the vent cell is always covered
    assert p[25, 20] > p[25, 5]            # the axis is more likely than the margins


def test_probability_grows_with_time():
    g = south_plane()
    fc = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=100), seed=2)
    p1, p6, pall = fc.probability(1.0), fc.probability(6.0), fc.probability()
    assert np.all(p1 <= p6 + 1e-12) and np.all(p6 <= pall + 1e-12)


def test_arrival_quantile_is_consistent_with_probability():
    g = south_plane()
    fc = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=150), seed=3)
    t50 = fc.arrival_quantile(0.5)
    i, j = 30, 20
    if np.isfinite(t50[i, j]):
        assert fc.probability(t50[i, j])[i, j] >= 0.5 - 1e-9
        assert fc.probability(t50[i, j] * 0.999)[i, j] < 0.5 + 1e-9
    assert np.all(np.isnan(t50[fc.probability() < 0.5 - 1e-9]))


def test_stop_reasons_sum_to_one_and_sea_is_detected():
    g = south_plane(sea_rows=10)
    fc = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=50, max_length_m=LogNormal(1e9)), seed=4)
    fr = fc.stop_fractions()
    assert sum(fr.values()) == pytest.approx(1.0)
    assert fr["nodata"] > 0.9


def test_no_cell_on_nodata_is_ever_covered():
    g = south_plane(sea_rows=10)
    fc = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=50, max_length_m=LogNormal(1e9)), seed=5)
    assert fc.probability()[np.isnan(g.elev)].max() == 0


def test_reweighting_changes_probability_not_paths():
    g = south_plane()
    fc = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=20), seed=6)
    w = np.zeros(20)
    w[0] = 1
    only0 = fc.reweighted(w)
    assert set(np.unique(only0.probability())) <= {0.0, 1.0}
    with pytest.raises(ValueError):
        fc.reweighted(np.zeros(20))


def test_same_seed_same_forecast():
    g = south_plane()
    a = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=30), seed=7).probability()
    b = forecast(g, vent_at(g, 0, 20), LavaParams(n_paths=30), seed=7).probability()
    assert np.array_equal(a, b)


def test_vent_on_sea_is_rejected():
    g = south_plane(sea_rows=10)
    with pytest.raises(ValueError):
        forecast(g, vent_at(g, 55, 20), deterministic())


def test_probability_at_point_outside_grid_is_nan():
    g = south_plane()
    fc = forecast(g, vent_at(g, 0, 20), deterministic())
    assert math.isnan(probability_at(fc, -1e6, -1e6))
