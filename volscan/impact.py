"""Impact with a clock: from lava probability to buildings, roads, critical services and isolated neighbourhoods.

THE QUESTION AN EMERGENCY SERVICE ASKS
--------------------------------------
"What will we lose, with what probability, and in how many hours?" For each
asset in the exposure inventory, VolScan computes:
  - the probability that some ensemble member covers it by a given horizon;
  - the arrival hour (P10/P50/P90) among the members that reach it;
  - for the whole: the expected number of buildings and km of road affected,
    with their P10–P90 range across members;
  - which neighbourhoods would be ISOLATED: still standing, but with no road
    link to a safe hub (Los Llanos, El Paso, or the edge of the area), because
    the lava cuts the roads.

The exposure inventory for La Palma 2021 comes from public sources and
reflects the state BEFORE the eruption:
  - Buildings and roads: the Copernicus EMS EMSR546 inventory (8,879 building
    points and 6,747 road segments within the activation area), which also
    carries the final damage grading. That's our ground truth: 2,988 buildings
    destroyed.
  - Services and neighbourhoods: OpenStreetMap as of 1 Sep 2021 (historical
    Overpass query): schools, health facilities, police, fire stations,
    substations, irrigation reservoirs, places.
  - Road graph for isolation: OpenStreetMap as of 1 Sep 2021.

LIMITS, IN PLAIN WORDS
----------------------
- The CEMS inventory only covers the activation area (where the lava went),
  so it can't measure impact outside it. That's enough to validate, not to
  map the whole island. For the pre-eruptive scenario we use OSM.
- A building is a point. A lava strip passing 20 m away doesn't count, even
  though in reality it could reach it (the error depends on the 25 m grid).
- Isolation assumes that any road covered by lava is impassable, and that
  roads not covered stay passable (ash and gases also close roads; they're
  not modelled).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .assimilation import weighted_quantiles
from .geo import lonlat_to_utm28
from .grid import Grid
from .lava import LavaForecast

CRITICAL_AMENITY = {
    "school": "Colegio", "kindergarten": "Escuela infantil", "hospital": "Hospital", "clinic": "Centro de salud",
    "doctors": "Consultorio", "pharmacy": "Farmacia", "fire_station": "Bomberos", "police": "Policía",
    "townhall": "Ayuntamiento", "social_facility": "Centro social", "community_centre": "Centro cívico",
    "fuel": "Gasolinera", "marketplace": "Mercado", "place_of_worship": "Templo",
}
CRITICAL_OTHER = {("power", "substation"): "Subestación eléctrica", ("man_made", "water_works"): "Potabilizadora",
                  ("man_made", "wastewater_plant"): "Depuradora", ("man_made", "reservoir_covered"): "Depósito de agua",
                  ("landuse", "reservoir"): "Estanque de riego"}
PLACE_TYPES = {"town", "village", "hamlet", "suburb", "neighbourhood", "locality"}


@dataclass
class Exposure:
    grid: Grid
    bld_cell: np.ndarray            # flat cell per building (−1 outside)
    bld_destroyed: np.ndarray       # final CEMS grading == Destroyed
    bld_xy: np.ndarray              # (n, 2) UTM
    road_seg_cells: list            # list of arrays of cells per segment
    road_len_m: np.ndarray
    road_destroyed: np.ndarray
    road_lonlat: list               # coordinates per segment (for drawing)
    facilities: list                # dicts: name, kind, label, x, y, cell
    places: list                    # dicts: name, x, y, cell, node
    graph: dict = field(default_factory=dict)

    @property
    def n_buildings(self):
        return int((self.bld_cell >= 0).sum())


def _cell(grid: Grid, x, y):
    i, j = grid.xy_to_ij(x, y)
    i, j = np.asarray(i), np.asarray(j)
    ok = (i >= 0) & (i < grid.shape[0]) & (j >= 0) & (j < grid.shape[1])
    return np.where(ok, i * grid.shape[1] + j, -1)


def _sample_line(grid: Grid, lonlat: np.ndarray, step_m: float):
    x, y = lonlat_to_utm28(lonlat[:, 0], lonlat[:, 1])
    pts = [(x[0], y[0])]
    length = 0.0
    for k in range(1, len(x)):
        d = float(np.hypot(x[k] - x[k - 1], y[k] - y[k - 1]))
        length += d
        n = max(1, int(np.ceil(d / step_m)))
        for s in range(1, n + 1):
            pts.append((x[k - 1] + (x[k] - x[k - 1]) * s / n, y[k - 1] + (y[k] - y[k - 1]) * s / n))
    p = np.array(pts)
    c = _cell(grid, p[:, 0], p[:, 1])
    return np.unique(c[c >= 0]), length


def load_exposure(grid: Grid, folder: Path) -> Exposure:
    b = json.loads((folder / "cems_builtup_grading.geojson").read_text())["features"]
    bll = np.array([f["geometry"]["coordinates"][:2] for f in b], float)
    bx, by = lonlat_to_utm28(bll[:, 0], bll[:, 1])
    bld_cell = _cell(grid, bx, by)
    bld_destroyed = np.array([f["properties"]["damage_gra"] == "Destroyed" for f in b])

    t = json.loads((folder / "cems_transport_grading.geojson").read_text())["features"]
    seg_cells, seg_len, seg_des, seg_ll = [], [], [], []
    for f in t:
        g = f["geometry"]
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for ln in lines:
            a = np.asarray(ln, float)
            if len(a) < 2:
                continue
            cells, length = _sample_line(grid, a, grid.step / 2)
            seg_cells.append(cells)
            seg_len.append(length)
            seg_des.append(f["properties"]["damage_gra"] == "Destroyed")
            seg_ll.append(np.round(a[:, :2], 6).tolist())

    o = json.loads((folder / "osm_facilities_places_20210901.json").read_text())["elements"]
    facilities, places = [], []
    for e in o:
        tg = e.get("tags", {})
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        if lat is None:
            continue
        x, y = lonlat_to_utm28(lon, lat)
        cell = int(_cell(grid, float(x), float(y)))
        if tg.get("place") in PLACE_TYPES and tg.get("name"):
            places.append(dict(name=tg["name"], kind=tg["place"], x=float(x), y=float(y), lon=lon, lat=lat, cell=cell))
            continue
        label = CRITICAL_AMENITY.get(tg.get("amenity", ""))
        if not label:
            for (k, v), lab in CRITICAL_OTHER.items():
                if tg.get(k) == v:
                    label = lab
        if label:
            facilities.append(dict(name=tg.get("name") or label, kind=label, x=float(x), y=float(y), lon=lon, lat=lat,
                                   cell=cell, osm=f"{e['type']}/{e['id']}"))
    exp = Exposure(grid, bld_cell, bld_destroyed, np.column_stack([bx, by]), seg_cells, np.array(seg_len),
                   np.array(seg_des), seg_ll, facilities, places)
    exp.graph = build_road_graph(grid, folder / "osm_roads_20210901.json", places)
    return exp


def build_road_graph(grid: Grid, roads_file: Path, places: list, hubs=("Los Llanos de Aridane", "El Paso")):
    """Graph whose nodes are lava-grid cells crossed by OSM roads (as of 1 Sep 2021)."""
    ways = json.loads(roads_file.read_text())["elements"]
    edges = set()
    for w in ways:
        geom = w.get("geometry")
        if not geom or len(geom) < 2:
            continue
        a = np.array([[p["lon"], p["lat"]] for p in geom], float)
        x, y = lonlat_to_utm28(a[:, 0], a[:, 1])
        prev = None
        for k in range(len(x)):
            if k:
                d = float(np.hypot(x[k] - x[k - 1], y[k] - y[k - 1]))
                n = max(1, int(np.ceil(d / (grid.step / 2))))
                pts = [(x[k - 1] + (x[k] - x[k - 1]) * s / n, y[k - 1] + (y[k] - y[k - 1]) * s / n) for s in range(1, n + 1)]
            else:
                pts = [(x[0], y[0])]
            for px, py in pts:
                c = int(_cell(grid, px, py))
                if c < 0:
                    prev = None
                    continue
                if prev is not None and prev != c:
                    edges.add((min(prev, c), max(prev, c)))
                prev = c
    nodes = np.unique(np.array([c for e in edges for c in e], int)) if edges else np.array([], int)
    index = {int(c): k for k, c in enumerate(nodes)}
    ei = np.array([[index[a], index[b]] for a, b in edges], int) if edges else np.zeros((0, 2), int)
    rows, cols = grid.shape
    ni, nj = nodes // cols, nodes % cols
    # safe hubs: grid border (road leaves the area) + cells near the hub towns
    safe = (ni <= 1) | (ni >= rows - 2) | (nj <= 1) | (nj >= cols - 2)
    X = grid.west + (nj + 0.5) * grid.step
    Y = grid.north - (ni + 0.5) * grid.step
    for p in places:
        if p["name"] in hubs:
            safe |= np.hypot(X - p["x"], Y - p["y"]) < 400
    # each place → nearest road node (within 400 m)
    for p in places:
        d = np.hypot(X - p["x"], Y - p["y"])
        k = int(np.argmin(d)) if d.size else -1
        p["node"] = k if k >= 0 and d[k] < 400 else -1
    return dict(nodes=nodes, edges=ei, safe=safe, hubs=list(hubs))


# ---------------------------------------------------------------- forecasting impact
def _arrival_lookup(fc: LavaForecast, cells: np.ndarray):
    """Sparse arrivals restricted to `cells`: returns (cell, path, t) arrays."""
    sel = np.isin(fc.cell, cells)
    return fc.cell[sel], fc.path[sel], fc.t_h[sel]


def member_hits(fc: LavaForecast, cells_of_asset: list[np.ndarray], t_max: float) -> np.ndarray:
    """Boolean (n_assets, n_paths): does each member cover any cell of the asset by t_max?"""
    allc = np.unique(np.concatenate([c for c in cells_of_asset if c.size] or [np.array([], int)]))
    out = np.zeros((len(cells_of_asset), fc.n_paths), bool)
    if allc.size == 0:
        return out
    c, p, t = _arrival_lookup(fc, allc)
    ok = t <= t_max
    c, p = c[ok], p[ok]
    by_cell: dict[int, set] = {}
    for ci, pi in zip(c.tolist(), p.tolist()):
        by_cell.setdefault(ci, set()).add(pi)
    for a, cells in enumerate(cells_of_asset):
        s = set()
        for ci in cells.tolist():
            s |= by_cell.get(ci, set())
        if s:
            out[a, list(s)] = True
    return out


def member_arrival(fc: LavaForecast, cells_of_asset: list[np.ndarray]) -> np.ndarray:
    """(n_assets, n_paths) earliest arrival hour, NaN if never."""
    allc = np.unique(np.concatenate([c for c in cells_of_asset if c.size] or [np.array([], int)]))
    out = np.full((len(cells_of_asset), fc.n_paths), np.inf)
    if allc.size:
        c, p, t = _arrival_lookup(fc, allc)
        best: dict[tuple, float] = {}
        for ci, pi, ti in zip(c.tolist(), p.tolist(), t.tolist()):
            k = (ci, pi)
            if ti < best.get(k, np.inf):
                best[k] = ti
        by_cell: dict[int, list] = {}
        for (ci, pi), ti in best.items():
            by_cell.setdefault(ci, []).append((pi, ti))
        for a, cells in enumerate(cells_of_asset):
            for ci in cells.tolist():
                for pi, ti in by_cell.get(ci, ()):
                    if ti < out[a, pi]:
                        out[a, pi] = ti
    out[np.isinf(out)] = np.nan
    return out


@dataclass(frozen=True)
class ImpactSummary:
    horizon_h: float
    buildings_expected: float
    buildings_p10_p90: tuple
    road_km_expected: float
    road_km_p10_p90: tuple


def _weighted_count_quantiles(counts_per_member: np.ndarray, w: np.ndarray):
    q = weighted_quantiles(counts_per_member, w, (0.1, 0.9))
    return tuple(float(v) for v in q)


def impact(fc: LavaForecast, exp: Exposure, t_until: float, already_mask: np.ndarray | None = None) -> dict:
    """Impact by `t_until` (hours since the eruption began).

    `already_mask` (flat cells already covered by observed lava) separates what
    is already lost from what is still to come: the forecast counts NEW losses
    only.
    """
    w = fc.weights
    lost_b = np.zeros(exp.bld_cell.shape, bool)
    if already_mask is not None:
        lost_b = (exp.bld_cell >= 0) & already_mask[np.clip(exp.bld_cell, 0, None)]
    b_cells = [np.array([c]) if (c >= 0 and not lost) else np.array([], int) for c, lost in zip(exp.bld_cell, lost_b)]
    hits_b = member_hits(fc, b_cells, t_until)                 # (n_b, n_paths)
    p_b = hits_b.astype(float) @ w
    count_b = hits_b.sum(axis=0).astype(float)

    lost_r = np.array([bool(already_mask is not None and c.size and already_mask[c].any()) for c in exp.road_seg_cells])
    r_cells = [c if not lost else np.array([], int) for c, lost in zip(exp.road_seg_cells, lost_r)]
    hits_r = member_hits(fc, r_cells, t_until)
    km_r = (hits_r * exp.road_len_m[:, None]).sum(axis=0) / 1000.0

    fac_cells = [np.array([f["cell"]]) if f["cell"] >= 0 else np.array([], int) for f in exp.facilities]
    arr_f = member_arrival(fc, fac_cells)
    facilities = []
    for f, arr in zip(exp.facilities, arr_f):
        reached = np.isfinite(arr) & (arr <= t_until)
        p = float(w[reached].sum())
        lost = bool(already_mask is not None and f["cell"] >= 0 and already_mask[f["cell"]])
        if p >= 0.01 or lost:
            q = weighted_quantiles(np.where(np.isfinite(arr), arr, np.nan), w, (0.1, 0.5, 0.9))
            facilities.append(dict(name=f["name"], kind=f["kind"], lon=f["lon"], lat=f["lat"], p=round(p, 3),
                                   already_lost=lost, eta_h=[None if np.isnan(v) else round(v, 1) for v in q]))
    facilities.sort(key=lambda d: (-d["already_lost"], -d["p"]))
    return dict(
        horizon_h=t_until,
        already_lost=dict(buildings=int(lost_b.sum()), road_km=round(float(exp.road_len_m[lost_r].sum()) / 1000, 2)),
        buildings=dict(expected=round(float(p_b.sum()), 1), p10_p90=_weighted_count_quantiles(count_b, w)),
        road_km=dict(expected=round(float(km_r @ w), 2), p10_p90=_weighted_count_quantiles(km_r, w)),
        facilities=facilities,
        building_probability=p_b,         # per building (not serialised by the API)
    )


def isolation(fc: LavaForecast, exp: Exposure, t_until: float, already_mask: np.ndarray | None = None) -> list[dict]:
    """Probability that each neighbourhood is left with no road link to a safe hub by `t_until`."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    G = exp.graph
    nodes, edges, safe = G["nodes"], G["edges"], G["safe"]
    if nodes.size == 0:
        return []
    n = nodes.size
    node_of_cell = {int(c): k for k, c in enumerate(nodes)}
    c, p, t = _arrival_lookup(fc, nodes)
    ok = t <= t_until
    covered_by_member: dict[int, list] = {}
    for ci, pi in zip(c[ok].tolist(), p[ok].tolist()):
        covered_by_member.setdefault(pi, []).append(node_of_cell[ci])
    base_cut = np.zeros(n, bool)
    if already_mask is not None:
        base_cut = already_mask[nodes]
    places = [pl for pl in exp.places if pl.get("node", -1) >= 0]
    iso = np.zeros((len(places), fc.n_paths), bool)
    reached = np.zeros((len(places), fc.n_paths), bool)
    cache: dict = {}
    for m in range(fc.n_paths):
        cut = base_cut.copy()
        cut[covered_by_member.get(m, [])] = True
        key = cut.tobytes()
        if key not in cache:
            keep = ~cut[edges[:, 0]] & ~cut[edges[:, 1]]
            e = edges[keep]
            A = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
            _, lab = connected_components(A, directed=False)
            safe_labels = set(lab[safe & ~cut].tolist())
            cache[key] = (lab, safe_labels, cut)
        lab, safe_labels, cut_m = cache[key]
        for k, pl in enumerate(places):
            if cut_m[pl["node"]]:
                reached[k, m] = True
            elif lab[pl["node"]] not in safe_labels:
                iso[k, m] = True
    w = fc.weights
    out = []
    for k, pl in enumerate(places):
        pi, pr = float(iso[k] @ w), float(reached[k] @ w)
        if pi >= 0.01 or pr >= 0.01:
            out.append(dict(name=pl["name"], kind=pl["kind"], lon=pl["lon"], lat=pl["lat"],
                            p_isolated=round(pi, 3), p_reached=round(pr, 3)))
    out.sort(key=lambda d: -(d["p_isolated"] + d["p_reached"]))
    return out


def observed_losses(exp: Exposure, observed_mask: np.ndarray) -> dict:
    """What an observed extent (flat mask) has destroyed: the ground truth for validation."""
    b = (exp.bld_cell >= 0) & observed_mask[np.clip(exp.bld_cell, 0, None)]
    r = np.array([bool(c.size and observed_mask[c].any()) for c in exp.road_seg_cells])
    return dict(buildings=int(b.sum()), road_km=round(float(exp.road_len_m[r].sum()) / 1000, 2))


# ---------------------------------------------------------------- "where" from the ensemble, "how much" from the observed growth
def scale_to_area(p_cells: np.ndarray, area_ha: float, cell_ha: float, already: np.ndarray | None = None,
                  iters: int = 30) -> np.ndarray:
    """Rescales a probability map so the expected new area equals `area_ha` (capped at 1 per cell).

    Why: an ensemble of narrow paths says WHERE the lava is likely to go, but
    not HOW MUCH area it will cover. A long eruption floods kilometres
    sideways (in La Palma 2021, 1,241 ha). The recent area growth observed by
    Copernicus is the best estimate of how much will be covered in the next
    few hours. This function spreads that area over the cells the ensemble
    marks, in proportion to their probability.
    """
    p = np.asarray(p_cells, float).copy()
    if already is not None:
        p[already] = 0.0
    tot = float((p * cell_ha).sum())
    if area_ha <= 0 or tot <= 0:
        return np.zeros_like(p)
    s = area_ha / tot
    q = np.minimum(1.0, s * p)
    for _ in range(iters):
        cov = float((q * cell_ha).sum())
        if cov <= 0 or abs(cov - area_ha) < 1e-3 * max(area_ha, 1):
            break
        s *= area_ha / cov
        q = np.minimum(1.0, s * p)
        if q.max() >= 1.0 and float((q * cell_ha).sum()) < area_ha * 0.999 and np.all(q[p > 0] >= 1.0):
            break
    return q


def expected_from_cells(q: np.ndarray, exp: Exposure) -> dict:
    """Expected buildings and road km given per-cell probabilities q (independent per cell)."""
    b = exp.bld_cell
    bld = float(q[b[b >= 0]].sum())
    km = 0.0
    for cells, length in zip(exp.road_seg_cells, exp.road_len_m):
        if cells.size:
            km += float(1.0 - np.prod(1.0 - q[cells])) * length / 1000.0
    return dict(buildings=bld, road_km=km)
