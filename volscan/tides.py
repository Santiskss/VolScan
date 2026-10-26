"""Solunar factors: solid-Earth tide phase and lunar phase per earthquake, and the Schuster test.

THE HYPOTHESIS, MEASURED
------------------------
The pull of the Moon and the Sun deforms the solid Earth by tens of
centimetres, twice a day. In some volcanoes and faults, seismicity has been
seen to cluster at certain phases of that cycle (the literature on tidal
triggering). This module DOESN'T ASSUME any such correlation exists. For each
event it computes:
  - `tidal_phase`: position within the local semi-diurnal cycle of the tidal
    potential (0° = maximum, 180° = minimum).
  - `lunar_elongation`: Sun–Moon angle (0° new moon, 180° full moon). Spring
    tides happen at 0° and 180°, so the spring/neap cycle is 2 × elongation.
Then the Schuster test checks whether the phases are uniform. A small p means
"not uniform". It does not mean "caused by the tide".

WARNING ABOUT SWARMS: the Schuster test assumes independent events, and
volcanic swarms are not independent. `decluster` keeps the largest event in
each window of `hours`, which reduces that bias. Always report both
p-values (raw and declustered).

ASTRONOMY: low-precision formulas from the Astronomical Almanac (Moon ~0.3°,
Sun ~0.01°). For the phase of a ~12.4 h cycle, 0.3° in the Moon's position is
under 2 minutes of phase error. The potential is degree 2 (P2), in units
relative to the Moon's mean contribution. We use it for phase, not to model
stresses.
"""
from __future__ import annotations

import math

import numpy as np

JD_UNIX_EPOCH = 2440587.5
SUN_MOON_MASS_RATIO = 27_068_510.0
AU_IN_EARTH_RADII = 23_454.78
MOON_MEAN_DIST_ER = 60.27


def jd(ts) -> np.ndarray:
    return np.asarray(ts, float) / 86400.0 + JD_UNIX_EPOCH


def _sind(x):
    return np.sin(np.radians(x))


def _cosd(x):
    return np.cos(np.radians(x))


def moon_ecliptic(ts):
    """(lambda deg, beta deg, distance in Earth radii)."""
    T = (jd(ts) - 2451545.0) / 36525.0
    lam = (218.32 + 481267.881 * T + 6.29 * _sind(135.0 + 477198.87 * T) - 1.27 * _sind(259.3 - 413335.36 * T)
           + 0.66 * _sind(235.7 + 890534.22 * T) + 0.21 * _sind(269.9 + 954397.74 * T)
           - 0.19 * _sind(357.5 + 35999.05 * T) - 0.11 * _sind(186.5 + 966404.03 * T))
    beta = (5.13 * _sind(93.3 + 483202.02 * T) + 0.28 * _sind(228.2 + 960400.89 * T)
            - 0.28 * _sind(318.3 + 6003.15 * T) - 0.17 * _sind(217.6 - 407332.21 * T))
    par = (0.9508 + 0.0518 * _cosd(135.0 + 477198.87 * T) + 0.0095 * _cosd(259.3 - 413335.36 * T)
           + 0.0078 * _cosd(235.7 + 890534.22 * T) + 0.0028 * _cosd(269.9 + 954397.74 * T))
    return lam % 360.0, beta, 1.0 / _sind(par)


def sun_ecliptic(ts):
    """(lambda deg, beta=0, distance in Earth radii)."""
    n = jd(ts) - 2451545.0
    L = 280.460 + 0.9856474 * n
    g = 357.528 + 0.9856003 * n
    lam = L + 1.915 * _sind(g) + 0.020 * _sind(2 * g)
    R = 1.00014 - 0.01671 * _cosd(g) - 0.00014 * _cosd(2 * g)
    return lam % 360.0, np.zeros_like(lam), R * AU_IN_EARTH_RADII


def _equatorial(lam, beta, ts):
    eps = 23.439 - 0.0000004 * (jd(ts) - 2451545.0)
    ra = np.degrees(np.arctan2(_sind(lam) * _cosd(eps) - np.tan(np.radians(beta)) * _sind(eps), _cosd(lam)))
    dec = np.degrees(np.arcsin(_sind(beta) * _cosd(eps) + _cosd(beta) * _sind(eps) * _sind(lam)))
    return ra % 360.0, dec


def gmst_deg(ts):
    return (280.46061837 + 360.98564736629 * (jd(ts) - 2451545.0)) % 360.0


def lunar_elongation(ts) -> np.ndarray:
    """Sun–Moon ecliptic longitude difference, 0..360 (0 new moon, 180 full moon)."""
    lm, _, _ = moon_ecliptic(ts)
    ls, _, _ = sun_ecliptic(ts)
    return (lm - ls) % 360.0


def tidal_potential(ts, lat, lon) -> np.ndarray:
    """Degree-2 tidal potential (Moon + Sun) at (lat, lon), in units of the Moon's mean amplitude."""
    out = 0.0
    for body, mass in ((moon_ecliptic, 1.0), (sun_ecliptic, SUN_MOON_MASS_RATIO)):
        lam, beta, d = body(ts)
        ra, dec = _equatorial(lam, beta, ts)
        H = gmst_deg(ts) + lon - ra
        cz = _sind(lat) * _sind(dec) + _cosd(lat) * _cosd(dec) * _cosd(H)
        scale = mass * (MOON_MEAN_DIST_ER / d) ** 3
        out = out + scale * (3 * cz * cz - 1) / 2
    return out


def tidal_phase(event_ts, lat, lon, step_s: float = 300.0) -> np.ndarray:
    """Phase (deg) of each event in the local tidal-potential cycle: 0 at the preceding maximum.

    The potential is computed at a single point (lat, lon), e.g. the centroid of
    a volcanic zone. That's valid for zones a few tens of km across: the
    phase shifts ~1° per 30 km in longitude.
    Events with no maximum before and after them (series edges) → NaN.
    """
    ev = np.asarray(event_ts, float)
    if ev.size == 0:
        return np.array([])
    t = np.arange(ev.min() - 86400, ev.max() + 86400 + step_s, step_s)
    w = tidal_potential(t, lat, lon)
    peaks = np.flatnonzero((w[1:-1] > w[:-2]) & (w[1:-1] >= w[2:])) + 1
    # sub-sample refinement (parabolic) of the peak times
    a, b, c = w[peaks - 1], w[peaks], w[peaks + 1]
    den = a - 2 * b + c
    off = np.where(den != 0, 0.5 * (a - c) / den, 0.0)
    tp = t[peaks] + off * step_s
    k = np.searchsorted(tp, ev, side="right")
    ok = (k > 0) & (k < tp.size)
    ph = np.full(ev.size, np.nan)
    prev, nxt = tp[np.clip(k - 1, 0, tp.size - 1)], tp[np.clip(k, 0, tp.size - 1)]
    ph[ok] = 360.0 * (ev[ok] - prev[ok]) / (nxt[ok] - prev[ok])
    return ph


def schuster(phases_deg) -> dict:
    """Schuster test for uniformity of phases. p = exp(-D²/N).

    Returns {n, p, mean_phase_deg, r} where r is the mean resultant length (0 uniform, 1 all the same).
    """
    ph = np.radians(np.asarray([p for p in np.asarray(phases_deg, float) if not math.isnan(p)]))
    n = ph.size
    if n == 0:
        return dict(n=0, p=float("nan"), mean_phase_deg=float("nan"), r=float("nan"))
    c, s = np.cos(ph).sum(), np.sin(ph).sum()
    d2 = c * c + s * s
    return dict(n=int(n), p=float(math.exp(-d2 / n)), mean_phase_deg=float(np.degrees(math.atan2(s, c)) % 360),
                r=float(math.sqrt(d2) / n))


def decluster(ts, mags, hours: float = 6.0) -> np.ndarray:
    """Boolean mask that keeps the largest event (by magnitude; earliest if tied or unknown) in each
    consecutive window of `hours`. A crude but transparent way to stop a swarm counting as thousands
    of independent trials."""
    ts = np.asarray(ts, float)
    m = np.nan_to_num(np.asarray(mags, float), nan=-99.0)
    bins = np.floor(ts / (hours * 3600.0)).astype(np.int64)
    keep = np.zeros(ts.size, bool)
    order = np.lexsort((ts, -m, bins))
    first = np.r_[True, bins[order][1:] != bins[order][:-1]]
    keep[order[first]] = True
    return keep
