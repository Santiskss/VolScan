import datetime as dt

import numpy as np
import pytest

from volscan import calibration as C
from volscan import deformation as D
from volscan.seismic import poisson_surprise
from volscan.sources import gibs_so2, ngl_gnss

TENV3 = """site YYMMMDD yyyy.yyyy __MJD week d reflon _e0(m) __east(m) ____n0(m) _north(m) u0(m) ____up(m) _ant(m) sig_e(m) sig_n(m) sig_u(m) __corr_en __corr_eu __corr_nu _latitude(deg) _longitude(deg) __height(m)
MAZO 10NOV22 2010.8912 55522 1611 1  -17.8   2016  0.351472   3165571  0.557619   526  0.227681  0.0000 0.000984 0.001075 0.004650  0.069710  0.092010  0.069787  28.6057332240  -17.7793824952   526.22768
MAZO 10NOV23 2010.8939 55523 1611 2  -17.8   2016  0.351286   3165571  0.556842   526  0.221355  0.0000 0.000936 0.000966 0.004482  0.006292  0.233268 -0.028339  28.6057332174  -17.7793824967   526.22135
"""


def test_parse_tenv3_joins_integer_and_fraction():
    t, lat, lon, e, n, u = ngl_gnss.parse_tenv3(TENV3)
    assert t.size == 2 and lat[0] == pytest.approx(28.6057, abs=1e-4)
    assert e[0] == pytest.approx(2016.351472) and u[1] == pytest.approx(526.221355)


def test_steps_are_parsed_and_removed():
    st = ngl_gnss.parse_steps("FRON  25APR23  1  Antenna_Type_Changed\nSNMG  10JUN14  2  12.3 earthquake\n")
    assert st == {"FRON": [dt.date(2025, 4, 23)]}
    t = np.arange(2025.0, 2025.6, 1 / 365.25)
    x = np.where(t >= ngl_gnss.date_to_decyear(dt.date(2025, 4, 23)), 0.015, 0.0)
    y = ngl_gnss.remove_steps(t, x, st["FRON"])
    assert np.ptp(y) < 1e-9


def _series(days, u_mm):
    return dict(code="TEST", place="", lat=0, lon=0, day=np.asarray(days), e=np.zeros(len(days)), n=np.zeros(len(days)),
                u=np.asarray(u_mm, float), zone="la_palma")


def test_station_anomaly_flags_uplift_not_steady_trend():
    rng = np.random.default_rng(0)
    d0 = dt.date(2018, 1, 1).toordinal()
    days = np.arange(d0, d0 + 4 * 365)
    trend = 3.0 * (days - d0) / 365.25 + rng.normal(0, 2, days.size)        # 3 mm/yr, steady
    quiet = D.station_anomaly(_series(days, trend), dt.date.fromordinal(int(days[-1])))
    bump = trend.copy()
    bump[-30:] += 40                                                          # 4 cm of sudden uplift
    loud = D.station_anomaly(_series(days, bump), dt.date.fromordinal(int(days[-1])))
    assert quiet["level"] == "normal"
    assert loud["level"] == "anómala" and loud["anom_u_mm"] == pytest.approx(40, abs=4)


def test_so2_colormap_decode_and_mass():
    xml = ('<ColorMapEntry rgb="8,40,100" transparent="false" sourceValue="[-INF,1.000)" value="[-INF,1.000)" ref="1"/>'
           '<ColorMapEntry rgb="200,10,10" transparent="false" sourceValue="[10.000,10.125)" value="[10.000,10.125)" ref="2"/>')
    lut = gibs_so2.parse_colormap(xml)
    assert lut[(200 << 16) | (10 << 8) | 10] == 10.0 and lut[(8 << 16) | (40 << 8) | 100] == 0.0
    du = np.full((10, 10), np.nan)
    du[0, 0] = 10.0
    kt, mx = gibs_so2.mass_kt(du, box=(0.0, 0.0, 1.0, 1.0))
    # one 0.1° x 0.1° pixel at 10 DU near the equator: 10 * 0.02854 g/m2 * (11.1 km)^2 ≈ 35 t
    assert kt == pytest.approx(0.0353, rel=0.05) and mx == 10.0


def test_so2_availability_periods():
    caps = ("<ows:Identifier>L1</ows:Identifier><Value>2021-01-01/2021-12-31/P1D</Value><Value>2022-02-01/2022-03-01/P1D</Value>"
            "</Layer>")
    per = gibs_so2.availability(caps, "L1")
    assert gibs_so2.covered(per, dt.date(2021, 9, 19)) and not gibs_so2.covered(per, dt.date(2022, 1, 15))


def test_poisson_surprise():
    assert poisson_surprise(2, 3.0) == 0.0
    assert poisson_surprise(30, 1.0) > 20
    assert 1.0 < poisson_surprise(8, 3.0) < 2.5


def test_calibration_episodes_and_outcomes():
    days = [dt.date(2021, 1, 1) + dt.timedelta(days=2 * k) for k in range(200)]
    ix = [0.0] * 200
    for k in range(20, 25):
        ix[k] = 6.0               # Feb 2021 swarm, no eruption
    for k in range(126, 131):
        ix[k] = 7.0               # 9–17 Sep 2021, right before the eruption
    eps = C.episodes(list(zip(days, ix)), 5)
    assert len(eps) == 2
    assert C.classify("la_palma", eps[0]) == "sin erupción"
    assert C.classify("la_palma", eps[1]) == "precedió a la erupción"
