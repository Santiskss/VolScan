"""Polygon rasterisation onto a Grid, and comparison metrics between masks.

Rasterisation uses the even-odd rule on cell centres. A cell counts as inside
when its centre is inside. Holes and multipolygons come out right because the
even-odd rule handles them on its own. We don't simplify, buffer or fill
anything.
"""
from __future__ import annotations

import numpy as np

from .geo import lonlat_to_utm28
from .grid import Grid


def _rings_xy(polygons_lonlat):
    """MultiPolygon coordinates (lon/lat) → list of rings as (N, 2) arrays in UTM 28N."""
    rings = []
    for poly in polygons_lonlat:
        for ring in poly:
            a = np.asarray(ring, float)
            x, y = lonlat_to_utm28(a[:, 0], a[:, 1])
            rings.append(np.column_stack([x, y]))
    return rings


def rasterize_rings(grid: Grid, rings_xy) -> np.ndarray:
    """Even-odd fill of rings (grid CRS metres) evaluated at cell centres → bool mask."""
    rows, cols = grid.shape
    mask = np.zeros((rows, cols), bool)
    ys = grid.north - (np.arange(rows) + 0.5) * grid.step
    xs = grid.west + (np.arange(cols) + 0.5) * grid.step
    for ring in rings_xy:
        if len(ring) < 3:
            continue
        x1, y1 = ring[:, 0], ring[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        lo, hi = max(0, int((grid.north - y1.max()) / grid.step) - 1), min(rows, int((grid.north - y1.min()) / grid.step) + 2)
        for r in range(lo, hi):
            y = ys[r]
            crosses = (y1 > y) != (y2 > y)
            if not crosses.any():
                continue
            xc = x1[crosses] + (y - y1[crosses]) * (x2[crosses] - x1[crosses]) / (y2[crosses] - y1[crosses])
            # a centre is inside when an odd number of edges cross the ray going right from it
            counts = (xs[:, None] < xc[None, :]).sum(axis=1)
            mask[r] ^= (counts % 2 == 1)
    return mask


def rasterize_lonlat(grid: Grid, polygons_lonlat) -> np.ndarray:
    """MultiPolygon (lon/lat) → bool mask. Even-odd inside each polygon (holes), union across polygons,
    so two overlapping parts don't cancel each other out."""
    mask = np.zeros(grid.shape, bool)
    for poly in polygons_lonlat:
        mask |= rasterize_rings(grid, _rings_xy([poly]))
    return mask


def compare(pred: np.ndarray, obs: np.ndarray, valid: np.ndarray | None = None) -> dict:
    """Binary forecast vs. observation. Returns IoU (Jaccard), hit rate, false-alarm ratio, areas.

    `valid` restricts the comparison (e.g. to cells with terrain data).
    """
    pred = np.asarray(pred, bool)
    obs = np.asarray(obs, bool)
    if valid is not None:
        pred, obs = pred & valid, obs & valid
    tp = int((pred & obs).sum())
    fp = int((pred & ~obs).sum())
    fn = int((~pred & obs).sum())
    union = tp + fp + fn
    return dict(
        iou=tp / union if union else float("nan"),
        hit_rate=tp / (tp + fn) if (tp + fn) else float("nan"),
        false_alarm_ratio=fp / (tp + fp) if (tp + fp) else float("nan"),
        pred_cells=tp + fp, obs_cells=tp + fn, tp=tp, fp=fp, fn=fn,
    )


def brier(prob: np.ndarray, obs: np.ndarray, valid: np.ndarray | None = None) -> float:
    """Mean squared error of a probability map against a binary observation."""
    p = np.asarray(prob, float)
    o = np.asarray(obs, float)
    if valid is not None:
        p, o = p[valid], o[valid]
    return float(np.mean((p - o) ** 2)) if p.size else float("nan")
