"""Deformation (GNSS) and gas (satellite SO2) indicators, next to the seismic one.

A volcano committee looks at four things: seismicity, deformation, gases and
geochemistry. VolScan v0.2 only had seismicity. This module adds the two that
open data can cover today, with what each can and cannot see.

DEFORMATION
-----------
For each GNSS station and day D:
  - a linear trend (velocity) is fitted over the 3 years that end 30 days
    before D: that is the station's "normal";
  - D is the last day with data (NGL final series arrive with ~4 weeks of lag;
    the interface shows that date);
  - the anomaly is how far the median position of the last 30 days is from
    that trend, in mm (east, north, up);
  - it is compared with the station's own scatter around the trend (robust
    sigma of 30-day medians), which gives a z-score.
Level: |z| < 3 "normal"; 3–6 "a vigilar"; > 6 "anómala". The thresholds
are deliberately high: seasonal loading and antenna problems produce a few
mm. A level is shown only for stations with data in the last 45 days.

GAS
---
SO2 mass visible from space above 1 DU around the archipelago (see
volscan.sources.gibs_so2). Over two quiet years (Oct 2024 – Oct 2026) the
daily maximum was 0.13 kt. We flag "SO2 detectado" from 1 kt.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import numpy as np

from .datasets import DATA
from .sources import gibs_so2, ngl_gnss

GNSS_DIR = DATA / "canarias" / "gnss"
SO2_CSV = DATA / "canarias" / "so2_omps_daily.csv"
SO2_DETECT_KT = 1.0
Z_WATCH, Z_ANOM = 3.0, 6.0
FRESH_DAYS = 45


@lru_cache(maxsize=1)
def load_gnss(folder: str = str(GNSS_DIR)) -> dict[str, dict]:
    out = {}
    for f in sorted(Path(folder).glob("*.csv.gz")):
        s = ngl_gnss.read_series(f)
        s["zone"], s["place"] = ngl_gnss.STATIONS.get(s["code"], ("atlantico", ""))
        out[s["code"]] = s
    return out


def _robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if x.size < 5:
        return float("nan")
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def station_anomaly(s: dict, day: dt.date, recent_days: int = 30, fit_years: float = 3.0) -> dict | None:
    """Anomaly of the last `recent_days` against the trend of the previous `fit_years`."""
    have = s["day"] <= day.toordinal()
    if not have.any():
        return None
    last = int(s["day"][have].max())
    stale = day.toordinal() - last > FRESH_DAYS
    D = last                       # evaluate at the last day with data (NGL final series lag ~4 weeks)
    recent = have & (s["day"] > D - recent_days)
    fit = (s["day"] <= D - recent_days) & (s["day"] > D - recent_days - int(fit_years * 365.25))
    if recent.sum() < 7 or fit.sum() < 365:
        return dict(code=s["code"], place=s["place"], lat=s["lat"], lon=s["lon"], last=dt.date.fromordinal(last).isoformat(),
                    level="sin datos", reason="pocos datos recientes o menos de un año de historia")
    t = (s["day"] - D) / 365.25
    out = dict(code=s["code"], place=s["place"], lat=s["lat"], lon=s["lon"], last=dt.date.fromordinal(last).isoformat())
    zs = {}
    for comp in ("e", "n", "u"):
        x = s[comp]
        A = np.vstack([t[fit], np.ones(fit.sum())]).T
        coef, *_ = np.linalg.lstsq(A, x[fit], rcond=None)
        resid = x - (coef[0] * t + coef[1])
        anom = float(np.median(resid[recent]))
        # scatter of 30-day medians of the residual within the fit window
        days = s["day"][fit]
        rf = resid[fit]
        meds = []
        for a in range(int(days.min()), int(days.max()) - recent_days, recent_days):
            w = (days > a) & (days <= a + recent_days)
            if w.sum() >= 7:
                meds.append(np.median(rf[w]))
        sig = max(_robust_sigma(np.array(meds)), 1.0 if comp != "u" else 2.0)
        out[f"anom_{comp}_mm"] = round(anom, 1)
        out[f"vel_{comp}_mm_yr"] = round(float(coef[0]), 1)
        zs[comp] = anom / sig
    zh = float(np.hypot(zs["e"], zs["n"]))
    zmax = max(zh, abs(zs["u"]))
    out.update(z_h=round(zh, 1), z_u=round(zs["u"], 1),
               level="normal" if zmax < Z_WATCH else "a vigilar" if zmax < Z_ANOM else "anómala")
    out["evaluated_at"] = dt.date.fromordinal(D).isoformat()
    if stale:
        out["level"] = "sin datos recientes"
    return out


def displacement_since(s: dict, ref: dt.date, day: dt.date, ref_days: int = 10) -> dict | None:
    """Position on `day` (3-day median) minus the median of the `ref_days` before `ref`, in mm."""
    R, D = ref.toordinal(), day.toordinal()
    base = (s["day"] < R) & (s["day"] >= R - ref_days)
    now = (s["day"] <= D) & (s["day"] > D - 3)
    if base.sum() < 3 or not now.any():
        return None
    return {c: round(float(np.median(s[c][now]) - np.median(s[c][base])), 1) for c in ("e", "n", "u")}


def zone_deformation(zone: str, day: dt.date) -> dict:
    st = [station_anomaly(s, day) for s in load_gnss().values() if s["zone"] == zone]
    st = [x for x in st if x]
    rank = {"anómala": 3, "a vigilar": 2, "normal": 1}
    levels = [x["level"] for x in st if x["level"] in rank]
    level = max(levels, key=rank.get) if levels else "sin datos"
    return dict(zone=zone, level=level, stations=st, citation=ngl_gnss.CITATION)


@lru_cache(maxsize=1)
def _so2_rows(path: str = str(SO2_CSV)) -> tuple:
    return tuple(gibs_so2.read_csv(Path(path)))


def so2_series(start: dt.date, end: dt.date) -> list[dict]:
    a, b = start.isoformat(), end.isoformat()
    return [r for r in _so2_rows() if a <= r["date"] <= b]


def so2_status(day: dt.date, window_days: int = 7) -> dict:
    rows = so2_series(day - dt.timedelta(days=window_days - 1), day)
    if not rows:
        return dict(level="sin datos", max_kt=None, last=None, citation=gibs_so2.CITATION)
    mx = max(rows, key=lambda r: r["so2_kt"])
    return dict(level="SO2 detectado" if mx["so2_kt"] >= SO2_DETECT_KT else "sin SO2 visible",
                max_kt=mx["so2_kt"], max_date=mx["date"], last=rows[-1]["date"], window_days=window_days,
                threshold_kt=SO2_DETECT_KT, citation=gibs_so2.CITATION)


def clear_caches():
    load_gnss.cache_clear()
    _so2_rows.cache_clear()
