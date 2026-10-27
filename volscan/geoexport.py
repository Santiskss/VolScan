"""From VolScan rasters to vector shapes other systems can read (GeoJSON, CAP, OGC API Features).

A probability raster becomes polygons by tracing the outline of the cells at
or above a threshold, exactly along the cell edges (like GDAL's polygonize),
then simplifying with Douglas–Peucker to a tolerance of about one cell. Holes
(unburnt islands inside a flow) are kept for GeoJSON; CAP polygons have no
holes, so only outer rings go there.

No GIS library is needed: everything is numpy, and coordinates go through
volscan.geo (UTM 28N ↔ WGS84).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .geo import utm28_to_lonlat
from .grid import Grid


def mask_rings(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """Closed rings along cell edges, in (col, row) corner coordinates. Outer rings counter-clockwise
    in map orientation (row grows southwards), holes clockwise."""
    m = np.pad(mask.astype(bool), 1)
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    r, c = np.nonzero(m)
    for rr, cc in zip(r.tolist(), c.tolist()):
        # each edge oriented with the cell on its left (in row-down coordinates that gives clockwise screen order)
        if not m[rr - 1, cc]:
            nxt[(cc + 1, rr)].append((cc, rr))           # top edge, right → left
        if not m[rr + 1, cc]:
            nxt[(cc, rr + 1)].append((cc + 1, rr + 1))   # bottom edge, left → right
        if not m[rr, cc - 1]:
            nxt[(cc, rr)].append((cc, rr + 1))           # left edge, top → bottom
        if not m[rr, cc + 1]:
            nxt[(cc + 1, rr + 1)].append((cc + 1, rr))   # right edge, bottom → top
    rings = []
    while nxt:
        start = next(iter(nxt))
        ring = [start]
        cur = start
        while True:
            outs = nxt.get(cur)
            if not outs:
                break
            n = outs.pop()
            if not outs:
                del nxt[cur]
            if n == start:
                break
            ring.append(n)
            cur = n
        if len(ring) >= 4:
            rings.append([(x - 1, y - 1) for x, y in ring])   # undo the padding
    return rings


def signed_area(ring) -> float:
    a = np.asarray(ring, float)
    x, y = a[:, 0], a[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def simplify(ring, tol: float):
    """Douglas–Peucker on a closed ring (keeps at least 4 points)."""
    pts = np.asarray(ring, float)
    if len(pts) <= 4 or tol <= 0:
        return [tuple(p) for p in pts]

    def dp(a: np.ndarray) -> np.ndarray:
        if len(a) <= 2:
            return a
        s, e = a[0], a[-1]
        d = e - s
        n = np.hypot(*d)
        v = a - s
        dist = np.abs(d[0] * v[:, 1] - d[1] * v[:, 0]) / n if n > 0 else np.hypot(v[:, 0], v[:, 1])
        k = int(np.argmax(dist))
        if dist[k] > tol:
            return np.vstack([dp(a[:k + 1])[:-1], dp(a[k:])])
        return np.vstack([s, e])

    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
    out = np.vstack([dp(pts[:far + 1])[:-1], dp(np.vstack([pts[far:], pts[:1]]))[:-1]])
    return [tuple(p) for p in out] if len(out) >= 4 else [tuple(p) for p in pts]


def _point_in_ring(x, y, ring) -> bool:
    a = np.asarray(ring, float)
    xs, ys = a[:, 0], a[:, 1]
    x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    cross = ((ys > y) != (y2 > y)) & (x < (x2 - xs) * (y - ys) / np.where(y2 - ys == 0, 1e-12, y2 - ys) + xs)
    return bool(cross.sum() % 2)


def to_lonlat(grid, ring):
    """`grid`: a UTM Grid, or a (lon0, lat1, res) tuple for a lon/lat raster."""
    a = np.asarray(ring, float)
    if isinstance(grid, tuple):
        lon0, lat1, res = grid
        lon, lat = lon0 + a[:, 0] * res, lat1 - a[:, 1] * res
    else:
        x = grid.west + a[:, 0] * grid.step
        y = grid.north - a[:, 1] * grid.step
        lon, lat = utm28_to_lonlat(x, y)
    pts = [[round(float(o), 6), round(float(t), 6)] for o, t in zip(lon, lat)]
    return pts + [pts[0]]


def mask_polygons(grid, mask: np.ndarray, tol_cells: float = 1.0, min_cells: int = 4) -> list[dict]:
    """GeoJSON Polygon geometries (lon/lat) with holes, for a boolean mask on `grid`."""
    rings = mask_rings(mask)
    outers, holes = [], []
    for r in rings:
        a = signed_area(r)
        if abs(a) < min_cells:
            continue
        (outers if a < 0 else holes).append(r)       # row-down coordinates flip the sign
    polys = []
    for o in outers:
        mine = [h for h in holes if _point_in_ring(h[0][0] + 0.5, h[0][1] + 0.5, o) or _point_in_ring(*h[0], o)]
        os_ = simplify(o, tol_cells)
        polys.append(dict(type="Polygon", coordinates=[to_lonlat(grid, os_)] +
                          [to_lonlat(grid, simplify(h, tol_cells)) for h in mine]))
    return polys


BANDS = ((0.5, 1.01, "probable", "≥ 50 %"), (0.2, 0.5, "posible", "20–50 %"), (0.05, 0.2, "poco probable", "5–20 %"))


def probability_bands(grid: Grid, p: np.ndarray, bands=BANDS, tol_cells: float = 1.5) -> list[dict]:
    """GeoJSON features: one MultiPolygon per probability band (cells with lo <= p < hi)."""
    feats = []
    for lo, hi, name, label in bands:
        m = (p >= lo) & (p < hi)
        if not m.any():
            continue
        polys = mask_polygons(grid, m, tol_cells)
        if polys:
            feats.append(dict(type="Feature", properties=dict(band=name, label=label, p_min=lo, p_max=min(hi, 1.0),
                                                              area_ha=round(float(m.sum()) * grid.step ** 2 / 1e4, 1)),
                              geometry=dict(type="MultiPolygon", coordinates=[q["coordinates"] for q in polys])))
    return feats


def feature_collection(features: list[dict], **props) -> dict:
    return dict(type="FeatureCollection", features=features, **props)
