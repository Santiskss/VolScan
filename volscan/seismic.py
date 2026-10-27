"""Seismic unrest analytics per volcanic zone.

WHAT THIS IS, AND WHAT IT ISN'T
-------------------------------
It describes how a zone's seismicity is changing compared with its own
history: how many events there are, at what depth, how they are distributed
in magnitude, and how much energy they release. Before Tajogaite (2021) and
Tagoro (2011), the swarm grew, got shallower and released accelerating
energy. Those are the precursors described in the literature.

The `unrest_index` IS NOT A PROBABILITY OF ERUPTION. It is a transparent
summary, in which each component can be checked separately. Plenty of swarms
in Canarias (Tenerife 2004, La Palma 2017-2020) ended without an eruption.
The official alert levels come from PEVOLCA, based on the IGN/INVOLCAN
evaluation.

Methods:
- b-value: Aki (1965) / Utsu maximum likelihood with half-bin correction,
  Mc by maximum curvature + 0.2 (Woessner & Wiemer 2005), Shi & Bolt (1982)
  uncertainty. With fewer than `min_events_b` events above Mc it returns None.
- Energy: log10 E[J] = 1.5 M + 4.8 (Gutenberg-Richter). The IGN mbLg and Mw
  scales differ; this is an order-of-magnitude indicator, not a seismic moment.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np

DAY = 86400.0


def energy_joules(mag) -> np.ndarray:
    m = np.asarray(mag, float)
    return 10 ** (1.5 * m + 4.8)


def mc_maxc(mags, bin_w: float = 0.1, correction: float = 0.2) -> float | None:
    m = np.asarray([x for x in mags if x is not None and not math.isnan(x)], float)
    if m.size < 20:
        return None
    bins = np.round(m / bin_w) * bin_w
    vals, counts = np.unique(np.round(bins, 3), return_counts=True)
    return float(vals[np.argmax(counts)] + correction)


@dataclass(frozen=True)
class BValue:
    b: float
    sigma: float
    mc: float
    n: int


def b_value(mags, bin_w: float = 0.1, mc: float | None = None, min_events_b: int = 50) -> BValue | None:
    m = np.asarray([x for x in mags if x is not None and not math.isnan(x)], float)
    if mc is None:
        mc = mc_maxc(m, bin_w)
    if mc is None:
        return None
    sel = m[m >= mc - 1e-9]
    n = sel.size
    if n < min_events_b:
        return None
    mean = sel.mean()
    denom = mean - (mc - bin_w / 2)
    if denom <= 0:
        return None
    b = math.log10(math.e) / denom
    sigma = 2.3 * b * b * math.sqrt(((sel - mean) ** 2).sum() / (n * (n - 1)))
    return BValue(b=b, sigma=sigma, mc=mc, n=n)


@dataclass
class Catalog:
    """Columnar catalogue: times in seconds since epoch (UTC)."""
    t: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    depth: np.ndarray      # km, NaN = unknown
    mag: np.ndarray        # NaN = unknown

    @classmethod
    def from_events(cls, events) -> "Catalog":
        def f(v):
            return np.nan if v is None else float(v)
        attr_t = "time_utc" if events and hasattr(events[0], "time_utc") else "time"
        attr_d = "depth_km"
        return cls(
            t=np.array([getattr(e, attr_t).timestamp() for e in events], float),
            lat=np.array([e.lat for e in events], float),
            lon=np.array([e.lon for e in events], float),
            depth=np.array([f(getattr(e, attr_d)) for e in events], float),
            mag=np.array([f(e.mag) for e in events], float),
        )

    def select(self, mask) -> "Catalog":
        return Catalog(self.t[mask], self.lat[mask], self.lon[mask], self.depth[mask], self.mag[mask])

    def window(self, start: float, end: float) -> "Catalog":
        return self.select((self.t >= start) & (self.t < end))

    def __len__(self):
        return self.t.size


@dataclass(frozen=True)
class WindowStats:
    n: int
    rate_per_day: float
    depth_median_km: float | None
    depth_trend_km_per_day: float | None    # negative = getting shallower
    energy_j: float
    max_mag: float | None
    b: BValue | None


def window_stats(cat: Catalog, start: float, end: float, min_events_b: int = 50) -> WindowStats:
    w = cat.window(start, end)
    days = (end - start) / DAY
    d = w.depth[~np.isnan(w.depth)]
    trend = None
    if d.size >= 10:
        td = w.t[~np.isnan(w.depth)] / DAY
        if np.ptp(td) > 0:
            trend = float(np.polyfit(td, d, 1)[0])
    m = w.mag[~np.isnan(w.mag)]
    return WindowStats(
        n=len(w), rate_per_day=len(w) / days if days > 0 else float("nan"),
        depth_median_km=float(np.median(d)) if d.size else None,
        depth_trend_km_per_day=trend,
        energy_j=float(energy_joules(m).sum()) if m.size else 0.0,
        max_mag=float(m.max()) if m.size else None,
        b=b_value(m, min_events_b=min_events_b),
    )


@dataclass(frozen=True)
class Unrest:
    at: float
    recent: WindowStats
    baseline: WindowStats
    rate_ratio: float | None
    energy_ratio: float | None
    shallowing_km: float | None          # baseline median depth − recent median depth (positive = shallower)
    index: float | None                  # 0..10, see `unrest`
    components: dict
    mc: float | None = None              # common completeness magnitude used for the counts
    rate_surprise: float | None = None   # −log10 Poisson P(N >= n_recent | baseline rate)
    energy_vs_worst_week: float | None = None


def _score(x, lo, hi):
    """Log-scale clamp: 0 at `lo`, 1 at `hi`."""
    if x is None or x <= 0:
        return 0.0
    return float(min(1.0, max(0.0, (math.log10(x) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))))


def poisson_surprise(n: int, mu: float) -> float:
    """−log10 P(N >= n) for N ~ Poisson(mu). 0 when n <= mu."""
    if n <= mu or mu <= 0:
        return 0.0 if n <= mu else 30.0
    from scipy.stats import poisson
    p = float(poisson.sf(n - 1, mu))
    return 30.0 if p <= 0 else min(30.0, -math.log10(p))


MIN_RECENT_ABOVE_MC = 5        # fewer events than this above Mc in a week: rate and energy can't score
MIN_DEPTHS = 20                # recent and baseline located events needed for the shallowing component


def unrest(cat: Catalog, at: float, recent_days: float = 7, baseline_days: float = 365,
           gap_days: float = 30) -> Unrest:
    """Compare the last `recent_days` against a baseline that ends `gap_days` earlier.

    The gap keeps the start of an ongoing swarm out of the baseline.

    Calibrated against 2011–2026 (see knowledge/metodologia_volscan.md, "índice"):
    raw ratios produced dozens of alarms in quiet zones, where three small
    events against a near-empty baseline look like "×10". So:
      - Counts only use events at or above a COMMON completeness magnitude
        (Mc by maximum curvature over baseline + recent). A denser network
        detects more small events; above Mc that doesn't change the count.
      - rate: how improbable the recent count is under the baseline rate
        (Poisson), 0 at p = 1, 1 at p = 1e-10. Not the ratio itself: ×10 on a
        rate of 0.1/day is noise, ×10 on 5/day is not.
      - energy: recent weekly energy against the most energetic week of the
        baseline year, 0 at ×1, 1 at ×100.
      - shallow: shallowing of the median depth, 0 at 0 km, 1 at ≥10 km, only
        with ≥ 20 located events in each window.
    Rate and energy need ≥ 5 recent events above Mc.
    index = 10 × mean of the available components. No baseline → None.
    """
    rs, re_ = at - recent_days * DAY, at
    be = rs - gap_days * DAY
    bs = be - baseline_days * DAY
    recent = window_stats(cat, rs, re_)
    base = window_stats(cat, bs, be)
    wr, wb = cat.window(rs, re_), cat.window(bs, be)
    both = np.r_[wr.mag, wb.mag]
    mc = mc_maxc(both[~np.isnan(both)])
    if mc is None:
        mr, mb = np.ones(len(wr), bool), np.ones(len(wb), bool)
    else:
        mr, mb = wr.mag >= mc - 1e-9, wb.mag >= mc - 1e-9
    n_r, n_b = int(mr.sum()), int(mb.sum())
    rate_ratio = (n_r / recent_days) / (n_b / baseline_days) if n_b > 0 else None
    surprise = poisson_surprise(n_r, n_b / baseline_days * recent_days) if n_b > 0 else None

    e_r = float(energy_joules(wr.mag[mr]).sum()) if n_r else 0.0
    e_base_day = float(energy_joules(wb.mag[mb]).sum()) / baseline_days if n_b else 0.0
    energy_ratio = (e_r / recent_days) / e_base_day if e_base_day > 0 else None
    worst = None
    if n_b:
        wk = np.floor((wb.t[mb] - bs) / (recent_days * DAY)).astype(int)
        worst = float(np.bincount(wk, weights=energy_joules(wb.mag[mb])).max())
    e_vs_worst = e_r / worst if worst else None

    shallow = None
    if recent.depth_median_km is not None and base.depth_median_km is not None and \
            (~np.isnan(wr.depth)).sum() >= MIN_DEPTHS and (~np.isnan(wb.depth)).sum() >= MIN_DEPTHS:
        shallow = base.depth_median_km - recent.depth_median_km
    enough = n_r >= MIN_RECENT_ABOVE_MC
    comps = {
        "rate": (min(1.0, surprise / 10) if enough else 0.0) if surprise is not None else None,
        "energy": (_score(e_vs_worst, 1, 100) if enough else 0.0) if e_vs_worst is not None else None,
        "shallow": float(min(1.0, max(0.0, shallow / 10))) if shallow is not None else None,
    }
    avail = [v for v in comps.values() if v is not None]
    index = 10 * float(np.mean(avail)) if base.n > 0 and avail else None
    return Unrest(at, recent, base, rate_ratio, energy_ratio, shallow, index, comps, mc, surprise, e_vs_worst)


def unrest_series(cat: Catalog, start: float, end: float, step_days: float = 1.0, **kw):
    """Unrest index sampled every `step_days` (list of (t, Unrest))."""
    out = []
    t = start
    while t <= end:
        out.append((t, unrest(cat, t, **kw)))
        t += step_days * DAY
    return out


def to_ts(d: dt.datetime) -> float:
    return d.timestamp()
