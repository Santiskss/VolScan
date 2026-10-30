import datetime as dt

import numpy as np
import pytest

from volscan.impact import scale_to_area
from volscan.reports import available_months, month_bounds, monthly_report, narrative
from volscan.seismic import Catalog
from volscan.sources.ign_catalog import IgnEvent


def test_scale_to_area_hits_target_and_caps_at_one():
    p = np.array([0.5, 0.25, 0.25, 0.0])
    q = scale_to_area(p, area_ha=2.0, cell_ha=1.0)
    assert q.max() <= 1.0 + 1e-12
    assert q.sum() == pytest.approx(2.0, rel=1e-3)
    assert q[3] == 0                                   # never invents lava where the ensemble says no


def test_scale_to_area_excludes_already_covered_cells():
    p = np.array([0.9, 0.1])
    q = scale_to_area(p, 0.05, 1.0, already=np.array([True, False]))
    assert q[0] == 0 and q[1] == pytest.approx(0.05, rel=1e-3)


def test_scale_to_area_cannot_exceed_available_cells():
    q = scale_to_area(np.array([0.2, 0.2]), area_ha=10, cell_ha=1.0)
    assert np.allclose(q, 1.0)


def test_month_bounds_and_list():
    a, b = month_bounds("2021-12")
    assert a.month == 12 and b.year == 2022 and b.month == 1
    t0 = dt.datetime(2021, 11, 30, tzinfo=dt.timezone.utc).timestamp()
    cat = Catalog(t=np.array([t0, t0 + 3 * 86400]), lat=np.zeros(2), lon=np.zeros(2), depth=np.zeros(2), mag=np.zeros(2))
    assert available_months(cat) == ["2021-12", "2021-11"]


def synth(n=200, month=(2026, 7)):
    rng = np.random.default_rng(1)
    a = dt.datetime(month[0], month[1], 1, tzinfo=dt.timezone.utc)
    ts = np.sort(a.timestamp() + rng.uniform(0, 28 * 86400, n))
    ev = [IgnEvent(str(k), dt.datetime.fromtimestamp(t, dt.timezone.utc), 28.27, -16.64, float(d), float(m), "mbLg",
                   "III" if k == 0 else "", "TEIDE.ITF")
          for k, (t, d, m) in enumerate(zip(ts, rng.normal(10, 2, n), np.round(rng.exponential(0.4, n) + 0.5, 1)))]
    cat = Catalog.from_events(ev)
    return cat, ev


def test_monthly_report_figures_and_narrative():
    cat, ev = synth()
    r = monthly_report(cat, ev, "tenerife", "2026-07", now=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
    assert r["stats"]["n"] == 200 and not r["partial"]
    assert len(r["daily"]) == 31 and sum(r["daily"]) == 200
    assert r["felt"] == 1
    assert "200 terremotos localizados" in r["summary"] and "1 fue sentido" in r["summary"]
    assert "PEVOLCA" in r["summary"]


def test_partial_month_says_so():
    cat, ev = synth()
    r = monthly_report(cat, ev, "tenerife", "2026-07", now=dt.datetime(2026, 7, 15, tzinfo=dt.timezone.utc))
    assert r["partial"] and "en lo que va de mes" in r["summary"]


def test_narrative_never_divides_by_missing_baseline():
    r = dict(zone=dict(name="X"), partial=False, stats=dict(n=0, max_mag=None, depth_median=None, shallow_lt5=0, n_m3=0),
             prev=dict(depth_median=None), rate_ratio=None, felt=0, unrest_end=dict(index=None), tides=None)
    assert narrative(r).startswith("X registró 0 terremotos localizados")


def test_validation_summary_counts_range_bias_and_watch():
    from volscan.replay import validation_summary
    rows = [dict(date="2021-09-25", pred_72=dict(expected=100, p10_p90=[50, 150]), obs_72=120,
                 watch=dict(high=10, high_hit=4, pocket=10, pocket_hit=2, lost=10)),
            dict(date="2021-10-25", pred_72=dict(expected=20, p10_p90=[5, 60]), obs_72=300,
                 watch=dict(high=10, high_hit=1, pocket=30, pocket_hit=9, lost=30)),
            dict(date="2021-10-26", pred_72=dict(expected=20, p10_p90=[5, 60]))]
    s = validation_summary(rows)
    assert s["days"] == 2 and s["within_p10_p90_72h"] == 1
    assert s["bias_pct"] == round(100 * (120 - 420) / 420, 1)
    assert s["watch"]["high"]["recall"] == round(5 / 40, 3)
    assert s["watch"]["with_pocket"]["recall"] == round(16 / 40, 3)


def test_impact_facility_eta_is_relative_to_t_now():
    from volscan.grid import Grid
    from volscan.impact import Exposure, impact
    from volscan.lava import LavaForecast
    g = Grid(elev=np.zeros((2, 2)), west=0.0, north=50.0, step=25.0)
    fc = LavaForecast(g, cell=np.array([1, 1]), path=np.array([0, 1]), t_h=np.array([120.0, 150.0]),
                      weights=np.array([0.5, 0.5]), stop_reason=np.array(["length", "length"]))
    exp = Exposure(g, bld_cell=np.array([1]), bld_destroyed=np.array([False]), bld_xy=np.zeros((1, 2)),
                   road_seg_cells=[], road_len_m=np.array([]), road_destroyed=np.array([], bool), road_lonlat=[],
                   facilities=[dict(name="Centro Salud", kind="Centro de salud", x=30.0, y=40.0, lon=-17.9, lat=28.6, cell=1)],
                   places=[])
    res = impact(fc, exp, t_until=172.0, t_now=100.0)
    assert res["facilities"][0]["eta_h"] == [20.0, 20.0, 50.0]


def test_catastrophe_report_lapalma2021_endpoint():
    from fastapi.testclient import TestClient
    from volscan.api.app import app

    c = TestClient(app)
    r = c.get("/api/reports/catastrophe/lapalma2021")
    assert r.status_code == 200
    body = r.json()
    assert len(body["provenance"]) == 7
    assert len(body["rheology_phases"]) == 3
    assert len(body["timeline"]) == 11
    assert body["tides_crisis"] is not None
    assert body["summary_kpis"]["volscan_days_within_p10_p90"] == 67

