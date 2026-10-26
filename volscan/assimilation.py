"""Lava-forecast assimilation: reweight ensemble members with observed lava extents.

Each observation (a CEMS polygon at time t, or a SAM 3.1 mask projected onto
the terrain) is used to judge every member by two things:

1. REACH: how far from the vent the member's front got by time t, compared
   with how far the observed flow got. The Gaussian likelihood is asymmetric.
   A member that falls short is penalised with `reach_sigma_m`. A member that
   runs ahead is penalised much less (`reach_sigma_fast_m`): real fronts stall
   for days and then advance again, and we don't want to throw those members
   away during a pause.
2. DIRECTION: the fraction of the cells the member had covered by time t that
   fall inside the observed flow. A member going down the wrong ravine scores
   close to 0. Its weight is raised to the power `direction_power`, with a
   floor of `direction_floor`, so one bad cell doesn't kill a member.

The likelihoods multiply across observations (assuming independent errors,
which they aren't, entirely), so we temper them with `temper` < 1 to avoid
collapsing the ensemble on a handful of members. We always report the
effective sample size (ESS): an ESS of 5 means "the ensemble has become
over-confident", and the UI says so.

The real lesson from La Palma 2021: the front stalled for days at about
3.6 km (22–26 Sep) and then reached the sea on 28 Sep. This model doesn't
represent effusion pulses, so while the front is stalled the ETA to the sea
widens or disappears. That's why we report alongside it whether the observed
AREA keeps growing while the reach doesn't: lava is building up, and a
breakout is possible.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .lava import LavaForecast


@dataclass(frozen=True)
class AssimParams:
    reach_sigma_m: float = 600.0          # member slower than observed
    reach_sigma_fast_m: float = 2500.0    # member faster than observed (fronts stall, then pulse again)
    direction_power: float = 2.0
    direction_floor: float = 0.05
    temper: float = 0.5


def member_reach(fc: LavaForecast, dist_flat: np.ndarray, t_h: float) -> np.ndarray:
    """Farthest distance from the vent (metres) covered by each member by time t_h."""
    sel = fc.t_h <= t_h
    r = np.zeros(fc.n_paths)
    np.maximum.at(r, fc.path[sel], dist_flat[fc.cell[sel]])
    return r


def member_precision(fc: LavaForecast, obs_mask_flat: np.ndarray, t_h: float,
                     dist_flat: np.ndarray | None = None, max_dist: float | None = None) -> np.ndarray:
    """Fraction of each member's covered cells (by t_h) that are inside the observed flow.

    With `dist_flat`/`max_dist`, only cells up to the observed reach count. A
    member that has run ahead of the observed front shouldn't be penalised for
    direction just because of the cells beyond that front: that's already
    judged by the reach likelihood.
    """
    sel = fc.t_h <= t_h
    if dist_flat is not None and max_dist is not None:
        sel &= dist_flat[fc.cell] <= max_dist
    inside = obs_mask_flat[fc.cell[sel]].astype(float)
    a = np.bincount(fc.path[sel], weights=inside, minlength=fc.n_paths)
    b = np.bincount(fc.path[sel], minlength=fc.n_paths)
    return np.where(b > 0, a / np.maximum(b, 1), 0.0)


def observed_reach(obs_mask_flat: np.ndarray, dist_flat: np.ndarray) -> float:
    return float(dist_flat[obs_mask_flat].max()) if obs_mask_flat.any() else 0.0


def log_likelihood(fc: LavaForecast, dist_flat, obs_mask_flat, t_h, p: AssimParams = AssimParams()):
    ro = observed_reach(obs_mask_flat, dist_flat)
    rm = member_reach(fc, dist_flat, t_h)
    pm = member_precision(fc, obs_mask_flat, t_h, dist_flat, ro + 200.0)
    sigma = np.where(rm > ro, p.reach_sigma_fast_m, p.reach_sigma_m)
    ll = -0.5 * ((rm - ro) / sigma) ** 2 + p.direction_power * np.log(np.maximum(pm, p.direction_floor))
    return p.temper * ll


def weights_from_loglik(total_ll: np.ndarray) -> np.ndarray:
    w = np.exp(total_ll - total_ll.max())
    return w / w.sum()


def ess(w: np.ndarray) -> float:
    return float(1.0 / np.sum(np.asarray(w) ** 2))


def weighted_quantiles(values, weights, qs):
    """Weighted quantiles over the members with a finite value. Returns NaN if none."""
    v = np.asarray(values, float)
    w = np.asarray(weights, float)
    ok = np.isfinite(v) & (w > 0)
    if not ok.any():
        return [float("nan")] * len(qs)
    v, w = v[ok], w[ok]
    o = np.argsort(v)
    cs = np.cumsum(w[o]) / w.sum()
    return [float(v[o][min(np.searchsorted(cs, q), v.size - 1)]) for q in qs]


def member_arrival_at(fc: LavaForecast, flat_cells) -> np.ndarray:
    """Earliest arrival (h) of each member at any of `flat_cells`. NaN if it never gets there."""
    target = np.zeros(fc.grid.elev.size, bool)
    target[np.asarray(flat_cells, int)] = True
    sel = target[fc.cell]
    out = np.full(fc.n_paths, np.inf)
    np.minimum.at(out, fc.path[sel], fc.t_h[sel])
    out[np.isinf(out)] = np.nan
    return out
