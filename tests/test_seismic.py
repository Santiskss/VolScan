import datetime as dt

import numpy as np
import pytest

from volscan.seismic import DAY, Catalog, b_value, energy_joules, mc_maxc, unrest, window_stats
from volscan.sources.ign_catalog import parse_rows, parse_total
from volscan.zones import zone_of


def gr_mags(n, b=1.0, mc=1.0, seed=0):
    rng = np.random.default_rng(seed)
    m = mc - 0.05 + rng.exponential(1 / (b * np.log(10)), n)
    return np.round(m, 1)


def test_b_value_recovers_synthetic_b():
    for b in (0.8, 1.0, 1.5):
        r = b_value(gr_mags(5000, b=b), mc=1.0)
        assert r.b == pytest.approx(b, rel=0.06)
        assert r.sigma < 0.05


def test_b_value_needs_enough_events():
    assert b_value(gr_mags(30), mc=1.0) is None


def test_mc_maxc_finds_the_mode_plus_correction():
    m = np.r_[np.full(10, 0.5), gr_mags(2000, mc=1.0)]
    assert mc_maxc(m) == pytest.approx(1.2, abs=0.11)


def test_energy_scale():
    assert energy_joules(2.0) / energy_joules(1.0) == pytest.approx(10 ** 1.5)


def synthetic_catalog():
    """One year of quiet background at 20 km, then a week-long shallow, intense swarm."""
    rng = np.random.default_rng(3)
    t0 = dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc).timestamp()
    tb = np.sort(rng.uniform(t0, t0 + 365 * DAY, 365))
    ts = np.sort(rng.uniform(t0 + 400 * DAY, t0 + 407 * DAY, 2000))
    t = np.r_[tb, ts]
    depth = np.r_[rng.normal(20, 3, tb.size), rng.normal(8, 2, ts.size)]
    mag = np.r_[gr_mags(tb.size, seed=4), gr_mags(ts.size, mc=1.5, seed=5)]
    cat = Catalog(t=t, lat=np.full(t.size, 28.6), lon=np.full(t.size, -17.85), depth=depth, mag=mag)
    return cat, t0


def test_unrest_is_low_in_background_and_high_in_swarm():
    cat, t0 = synthetic_catalog()
    quiet = unrest(cat, t0 + 360 * DAY, baseline_days=300, gap_days=10)
    swarm = unrest(cat, t0 + 407 * DAY)
    assert swarm.rate_ratio > 50
    assert swarm.shallowing_km == pytest.approx(12, abs=1.5)
    assert swarm.index > 7
    assert quiet.index < 3


def test_unrest_without_baseline_is_none_not_zero():
    cat, t0 = synthetic_catalog()
    u = unrest(cat, t0 + 1 * DAY)
    assert u.index is None and u.rate_ratio is None


def test_window_stats_depth_trend_sign():
    t = np.arange(0, 10 * DAY, DAY / 10)
    cat = Catalog(t=t, lat=t * 0, lon=t * 0, depth=20 - t / DAY, mag=np.full(t.size, 1.0))
    s = window_stats(cat, 0, 10 * DAY)
    assert s.depth_trend_km_per_day == pytest.approx(-1.0)


def test_zones():
    assert zone_of(28.61, -17.87).key == "la_palma"
    assert zone_of(27.62, -18.00).key == "el_hierro"
    assert zone_of(28.27, -16.64).key == "tenerife"
    assert zone_of(29.00, -13.75).key == "lanzarote_fuerteventura"   # Timanfaya
    assert zone_of(31.0, -10.0).key == "atlantico"
    assert zone_of(27.62, -17.99).key == "el_hierro"            # Tagoro, submarine, 2 km off La Restinga
    assert zone_of(28.10, -15.95).key == "enmedio"
    assert zone_of(28.27, -16.20).key == "tenerife"             # sea between the boxes of v0.1 still belongs to Tenerife


def test_zones_do_not_overlap_and_vectorise():
    import numpy as np
    from volscan.zones import zone_keys
    k = zone_keys(np.array([28.61, 27.95, 30.5]), np.array([-17.87, -15.6, -20.0]))
    assert list(k) == ["la_palma", "gran_canaria", "atlantico"]


IGN_PAGE = """<p>562 terremotos. </p><table><tr><th>Evento</th></tr>
<tr><td>1101108</td><td>01/10/2011</td><td>00:00:21</td><td>01:00:21</td><td>27.6543</td><td>-18.0519</td>
<td>10.3</td><td>2.5</td><td>mbLg</td><td></td><td>SW FRONTERA.IHI</td></tr>
<tr><td>es2021rchex</td><td>01/09/2021</td><td>02:45:43</td><td>03:45:43</td><td>28.2406</td><td>-16.6664</td>
<td></td><td>0.6</td><td>mbLg</td><td>II</td><td>NW VILAFLOR.ITF</td></tr></table>"""


def test_ign_page_parsing():
    rows = parse_rows(IGN_PAGE)
    assert parse_total(IGN_PAGE) == 562
    assert [r.evid for r in rows] == ["1101108", "es2021rchex"]
    assert rows[0].time_utc == dt.datetime(2011, 10, 1, 0, 0, 21, tzinfo=dt.timezone.utc)
    assert rows[1].depth_km is None and rows[1].int_max == "II"


def test_ign_total_with_thousands_separator():
    assert parse_total("<p>12.714 terremotos.</p>") == 12714
