import numpy as np
import pytest

from volscan import assimilation as A
from volscan.grid import Grid
from volscan.lava import LavaForecast


def toy_forecast():
    """1 x 10 strip, vent at column 0. Member 0 runs 1 cell/h, member 1 runs 3 cells/h."""
    g = Grid(elev=np.zeros((1, 10)), west=0, north=10, step=1.0)
    cells, paths, ts = [], [], []
    for p, speed in ((0, 1.0), (1, 3.0)):
        for c in range(10):
            cells.append(c)
            paths.append(p)
            ts.append(c / speed)
    fc = LavaForecast(g, np.array(cells), np.array(paths), np.array(ts), np.array([0.5, 0.5]),
                      np.array(["nodata", "nodata"]))
    dist = np.arange(10, dtype=float) + 0.5
    return fc, dist


def test_member_reach_and_precision():
    fc, dist = toy_forecast()
    assert A.member_reach(fc, dist, 3.0).tolist() == [3.5, 9.5]
    obs = np.zeros(10, bool)
    obs[:4] = True
    prec = A.member_precision(fc, obs, 3.0)
    assert prec[0] == 1.0 and prec[1] == pytest.approx(0.4)
    # restricted to the observed reach, the fast member is not penalised for running ahead
    assert A.member_precision(fc, obs, 3.0, dist, 4.0)[1] == 1.0


def test_observation_favours_the_member_that_matches():
    fc, dist = toy_forecast()
    obs = np.zeros(10, bool)
    obs[:4] = True                       # front at ~3.5 at t=3 -> member 0
    p = A.AssimParams(reach_sigma_m=1.0, reach_sigma_fast_m=1.0, temper=1.0)
    w = A.weights_from_loglik(A.log_likelihood(fc, dist, obs, 3.0, p))
    assert w[0] > 0.99


def test_fast_members_survive_a_stall_better_than_slow_ones():
    fc, dist = toy_forecast()
    obs = np.zeros(10, bool)
    obs[:7] = True                       # reach 6.5 at t=3: member 0 is 3 short, member 1 is 3 ahead
    w = A.weights_from_loglik(A.log_likelihood(fc, dist, obs, 3.0, A.AssimParams(reach_sigma_m=2, reach_sigma_fast_m=10, temper=1)))
    assert w[1] > w[0]


def test_weighted_quantiles_and_ess():
    v = np.array([1.0, 2.0, np.nan, 10.0])
    w = np.array([0.25, 0.25, 0.25, 0.25])
    assert A.weighted_quantiles(v, w, (0.5,))[0] == 2.0
    assert np.isnan(A.weighted_quantiles([np.nan], [1.0], (0.5,))[0])
    assert A.ess(np.full(4, 0.25)) == pytest.approx(4)


def test_member_arrival_at_target_cells():
    fc, _ = toy_forecast()
    arr = A.member_arrival_at(fc, [6])
    assert arr.tolist() == [6.0, 2.0]
