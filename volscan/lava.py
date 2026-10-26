"""Probabilistic lava flow forecast: an ensemble of stochastic steepest-descent paths.

THE MODEL, AND WHY
------------------
Lava goes downhill. Across an ensemble, how far it goes and which branch it
takes are uncertain. The topographic method we use is that of DOWNFLOW
(Favalli et al., 2005, GRL 32, L03305), which has been validated on Etna and
on other basaltic systems:

1. Every ensemble member perturbs the terrain with uniform noise of ±dh metres.
   That stands for the DEM error, for topography the lava builds itself, and
   for small obstacles. It then follows the steepest descent from the vent.
   Where nothing is lower, the flow overtops the obstacle if it doesn't have to
   climb more than its own thickness (see `trace_path`).
2. A path stops when it reaches its maximum length (which stands for the
   volume and effusion rate that we don't know), a pit, the grid edge, or a
   no-data cell. In a coastal grid, no-data is usually the sea. We report that
   as "no-data", not "sea", because it can also be a gap in the source.
3. Each path covers a strip around it of half-width w. Real flows are hundreds
   of metres wide, and a single-cell path is not.

The DOWNFLOW authors calibrate dh and the number of paths against real flows.
We do the same against the Copernicus EMS lava extents of La Palma 2021
(see `volscan.backtest`). The defaults below are a starting point, NOT a
calibration.

TIMING (what DOWNFLOW doesn't give you)
---------------------------------------
For arrival times, we move each path's front with the Jeffreys velocity of a
laminar Newtonian sheet:

    v = rho * g * h^2 * sin(theta) / (3 * eta)

where h is the flow thickness, eta the bulk viscosity and theta the real
(unperturbed) slope of each step. Real fronts are limited by supply and
cooling. So eta and h are *effective* parameters, sampled from wide
distributions and meant to be corrected by observations (assimilation). They
are not measured properties of the lava.

Below `min_slope_deg`, the slope is clamped to that minimum. On flat ground,
flows keep advancing slowly as they thicken. Without the clamp, the front
would stop forever, and that would be a modelling artefact.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np

from .grid import Grid

G = 9.81
STOP_REASONS = ("length", "pit", "edge", "nodata")

# 8-neighbourhood: (di, dj, distance factor)
_NEIGH = [(-1, -1, math.sqrt(2)), (-1, 0, 1.0), (-1, 1, math.sqrt(2)),
          (0, -1, 1.0), (0, 1, 1.0),
          (1, -1, math.sqrt(2)), (1, 0, 1.0), (1, 1, math.sqrt(2))]


@dataclass(frozen=True)
class LogNormal:
    """Log-normal parameter given by its median and the sigma of its natural log."""
    median: float
    sigma: float = 0.0

    def sample(self, rng: np.random.Generator, n: int) -> np.ndarray:
        if self.sigma <= 0:
            return np.full(n, float(self.median))
        return self.median * np.exp(rng.normal(0.0, self.sigma, n))


@dataclass(frozen=True)
class LavaParams:
    n_paths: int = 500
    dh_m: float = 3.0                                   # terrain noise amplitude (±)
    max_length_m: LogNormal = LogNormal(6000.0, 0.5)
    half_width_m: LogNormal = LogNormal(150.0, 0.4)
    thickness_m: LogNormal = LogNormal(8.0, 0.3)
    viscosity_pa_s: LogNormal = LogNormal(1.0e6, 1.0)
    density_kg_m3: float = 2500.0
    min_slope_deg: float = 1.0
    vent_sigma_m: float = 100.0                         # vent location uncertainty (1-sigma)
    overtop: bool = True                                # flows overtop obstacles up to their thickness


@dataclass
class LavaForecast:
    """Ensemble result in sparse form: one row per (path, cell) it covers, with the earliest arrival."""
    grid: Grid
    cell: np.ndarray            # flat cell index
    path: np.ndarray            # path id
    t_h: np.ndarray             # arrival time, hours after the eruption starts
    weights: np.ndarray         # one per path, sums to 1
    stop_reason: np.ndarray     # one per path, from STOP_REASONS
    members: dict = field(default_factory=dict)   # sampled parameters per path (arrays)

    @property
    def n_paths(self) -> int:
        return len(self.weights)

    def probability(self, t_h: float | None = None) -> np.ndarray:
        """Probability that each cell is covered by lava by time t_h (None = ever), shape = grid."""
        sel = slice(None) if t_h is None else self.t_h <= t_h
        p = np.bincount(self.cell[sel], weights=self.weights[self.path[sel]],
                        minlength=self.grid.elev.size)
        return p.reshape(self.grid.shape)

    def arrival_quantile(self, q: float) -> np.ndarray:
        """Per cell: earliest time by which the probability of being covered reaches q.

        NaN where the probability never reaches q. That isn't "safe": it means
        "the ensemble doesn't support it with probability q".
        """
        if not 0 < q <= 1:
            raise ValueError("q must be in (0, 1]")
        out = np.full(self.grid.elev.size, np.nan)
        if self.cell.size == 0:
            return out.reshape(self.grid.shape)
        order = np.lexsort((self.t_h, self.cell))
        c, t, w = self.cell[order], self.t_h[order], self.weights[self.path[order]]
        starts = np.r_[0, np.flatnonzero(np.diff(c)) + 1]
        cum = np.cumsum(w)
        base = np.repeat(cum[starts] - w[starts], np.diff(np.r_[starts, c.size]))
        within = cum - base
        hit = within >= q - 1e-12
        # first hit per cell
        hit_idx = np.flatnonzero(hit)
        first = np.unique(c[hit_idx], return_index=True)
        out[first[0]] = t[hit_idx[first[1]]]
        return out.reshape(self.grid.shape)

    def stop_fractions(self) -> dict:
        return {r: float(self.weights[self.stop_reason == r].sum()) for r in STOP_REASONS}

    def reweighted(self, weights: np.ndarray) -> "LavaForecast":
        """Same paths, new weights (used by assimilation)."""
        w = np.asarray(weights, float)
        if w.shape != self.weights.shape or np.any(w < 0) or not w.sum() > 0:
            raise ValueError("weights must be non-negative, one per path, not all zero")
        return LavaForecast(self.grid, self.cell, self.path, self.t_h, w / w.sum(),
                            self.stop_reason, self.members)


def _sample_vent(grid: Grid, vents, sigma_m, rng):
    xs = np.array([v[0] for v in vents], float)
    ys = np.array([v[1] for v in vents], float)
    pw = np.array([v[2] if len(v) > 2 else 1.0 for v in vents], float)
    pw = pw / pw.sum()
    for _ in range(100):
        k = rng.choice(len(vents), p=pw)
        x = xs[k] + rng.normal(0, sigma_m) if sigma_m > 0 else xs[k]
        y = ys[k] + rng.normal(0, sigma_m) if sigma_m > 0 else ys[k]
        i, j = grid.xy_to_ij(x, y)
        i, j = int(i), int(j)
        if grid.inside(i, j) and not math.isnan(grid.elev[i, j]):
            return i, j
    raise ValueError("could not place a vent on valid terrain; check vent coordinates and grid")


def _fill_and_spill(grid: Grid, zp, start, visited, max_rise_m: float, max_cells: int = 4000):
    """Fill the depression around `start`, as a pond rising level by level, until it spills.

    Priority-flood from the pit: we always flood the lowest cell on the pond's
    edge. The level is the highest elevation flooded so far. As soon as a
    flooded cell has an unvisited neighbour below the level, that is the
    outlet. If the level has to rise more than `max_rise_m` (the flow
    thickness) above the pit floor, or the pond grows beyond `max_cells`,
    the lava stays there.

    Returns (pond_cells, kind, outlet) where kind is 'outlet' | 'edge' | 'nodata',
    or None if the flow ponds for good.
    """
    floor = zp(*start)
    heap = [(floor, start)]
    seen = {start}
    level = floor
    pond = []
    while heap:
        zc, (ci, cj) = heapq.heappop(heap)
        level = max(level, zc)
        if level - floor > max_rise_m or len(pond) >= max_cells:
            return None
        pond.append((ci, cj))
        for di, dj, f in _NEIGH:
            ni, nj = ci + di, cj + dj
            if not grid.inside(ni, nj):
                return pond, "edge", None
            if math.isnan(grid.elev[ni, nj]):
                return pond, "nodata", None
            if (ni, nj) in seen:
                continue
            zn = zp(ni, nj)
            if zn < level and (ni, nj) not in visited:
                return pond, "outlet", (ni, nj, f, (ci, cj))
            seen.add((ni, nj))
            heapq.heappush(heap, (zn, (ni, nj)))
    return None


def trace_path(grid: Grid, start, dh_m: float, max_length_m: float, rng: np.random.Generator,
               max_climb_m: float = 0.0):
    """One stochastic steepest-descent path.

    With `max_climb_m` > 0, the flow can get out of hollows. When no neighbour
    is lower, the hollow fills like a pond (see `_fill_and_spill`), and the
    lava spills over the lowest point of its rim, as long as that point is no
    more than `max_climb_m` above the floor. A flow of thickness h doesn't stop
    at a small mound. With 0 (pure DOWNFLOW), the noise itself creates spurious
    pits on gentle slopes, and those cut the paths short. The pond cells count
    as covered by lava.

    Returns (cells [(i, j), ...], step lengths in metres, real drops in metres, stop_reason).
    The first cell is the vent, with step length 0. Pond cells have step 0.
    """
    z = grid.elev
    noise: dict = {}

    def zp(i, j):
        key = (i, j)
        if key not in noise:
            noise[key] = rng.uniform(-dh_m, dh_m) if dh_m > 0 else 0.0
        return z[i, j] + noise[key]

    i, j = start
    cells, steps, drops = [(i, j)], [0.0], [0.0]
    visited = {(i, j)}
    length = 0.0
    while True:
        here = zp(i, j)
        best, best_slope, hit_nodata, hit_edge = None, 0.0, False, False
        for di, dj, f in _NEIGH:
            ni, nj = i + di, j + dj
            if not grid.inside(ni, nj):
                hit_edge = True
                continue
            if math.isnan(z[ni, nj]):
                hit_nodata = True
                continue
            s = (here - zp(ni, nj)) / (f * grid.step)
            if s > best_slope and (ni, nj) not in visited:
                best, best_slope = (ni, nj, f), s
        if best is None:
            # No lower valid neighbour. If we're touching sea/gap or the edge,
            # lava would spill there; otherwise try to fill and spill.
            if hit_nodata or hit_edge:
                return cells, steps, drops, "nodata" if hit_nodata else "edge"
            res = _fill_and_spill(grid, zp, (i, j), visited, max_climb_m) if max_climb_m > 0 else None
            if res is None:
                return cells, steps, drops, "pit"
            pond, kind, outlet = res
            for c in pond:
                if c not in visited:
                    visited.add(c)
                    cells.append(c)
                    steps.append(0.0)
                    drops.append(0.0)
            if kind != "outlet":
                return cells, steps, drops, kind
            ni, nj, f, (i, j) = outlet
        else:
            ni, nj, f = best
        ds = f * grid.step
        if length + ds > max_length_m:
            return cells, steps, drops, "length"
        length += ds
        drops.append(float(z[i, j] - z[ni, nj]))
        i, j = ni, nj
        visited.add((i, j))
        cells.append((i, j))
        steps.append(ds)


def _front_times_h(steps, drops, h, eta, rho, min_slope_deg):
    steps = np.asarray(steps, float)
    drops = np.asarray(drops, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        theta = np.where(steps > 0, np.arctan2(drops, steps), 0.0)
    theta = np.maximum(theta, math.radians(min_slope_deg))
    v = rho * G * h * h * np.sin(theta) / (3.0 * eta)          # m/s
    dt = np.where(steps > 0, steps / v, 0.0)
    return np.cumsum(dt) / 3600.0


def _disk_offsets(radius_cells: float):
    r = int(math.floor(radius_cells))
    di, dj = np.mgrid[-r:r + 1, -r:r + 1]
    keep = di * di + dj * dj <= radius_cells * radius_cells + 1e-9
    return di[keep], dj[keep]


def forecast(grid: Grid, vents, params: LavaParams = LavaParams(), seed: int | None = 0) -> LavaForecast:
    """Run the ensemble.

    vents: list of (x, y) or (x, y, weight) in the grid CRS (metres).
    """
    if not vents:
        raise ValueError("at least one vent is required")
    rng = np.random.default_rng(seed)
    n = params.n_paths
    max_len = params.max_length_m.sample(rng, n)
    half_w = params.half_width_m.sample(rng, n)
    thick = params.thickness_m.sample(rng, n)
    eta = params.viscosity_pa_s.sample(rng, n)

    rows, cols = grid.shape
    valid = ~np.isnan(grid.elev).ravel()
    all_cell, all_path, all_t, reasons = [], [], [], []
    for p in range(n):
        start = _sample_vent(grid, vents, params.vent_sigma_m, rng)
        cells, steps, drops, reason = trace_path(grid, start, params.dh_m, max_len[p], rng,
                                                 max_climb_m=thick[p] if params.overtop else 0.0)
        reasons.append(reason)
        t = _front_times_h(steps, drops, thick[p], eta[p], params.density_kg_m3, params.min_slope_deg)
        pi = np.array([c[0] for c in cells])
        pj = np.array([c[1] for c in cells])
        oi, oj = _disk_offsets(half_w[p] / grid.step)
        ci = (pi[:, None] + oi[None, :]).ravel()
        cj = (pj[:, None] + oj[None, :]).ravel()
        ct = np.repeat(t, oi.size)
        ok = (ci >= 0) & (ci < rows) & (cj >= 0) & (cj < cols)
        flat = ci[ok] * cols + cj[ok]
        ct = ct[ok]
        ok2 = valid[flat]
        flat, ct = flat[ok2], ct[ok2]
        order = np.lexsort((ct, flat))
        flat, ct = flat[order], ct[order]
        first = np.r_[True, flat[1:] != flat[:-1]]
        all_cell.append(flat[first])
        all_t.append(ct[first])
        all_path.append(np.full(int(first.sum()), p))

    return LavaForecast(
        grid=grid,
        cell=np.concatenate(all_cell),
        path=np.concatenate(all_path),
        t_h=np.concatenate(all_t),
        weights=np.full(n, 1.0 / n),
        stop_reason=np.array(reasons),
        members=dict(max_length_m=max_len, half_width_m=half_w, thickness_m=thick, viscosity_pa_s=eta),
    )


def probability_at(fc: LavaForecast, x, y, t_h: float | None = None) -> float:
    """Probability that the point (x, y) is covered by time t_h. NaN if the point is outside the grid."""
    i, j = fc.grid.xy_to_ij(x, y)
    i, j = int(i), int(j)
    if not fc.grid.inside(i, j):
        return float("nan")
    return float(fc.probability(t_h)[i, j])
