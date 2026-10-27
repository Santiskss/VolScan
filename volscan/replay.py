"""La Palma 2021 replay: what VolScan would have known, day by day.

For each day we use ONLY information available by the end of that day:
seismicity up to that moment, and CEMS observations DELIVERED by that moment.
CEMS rapid-mapping delineations are delivered 7 h (fast mode) to 48 h
(standard mode) after the image is received. The layers don't record the
delivery time, so each map is assumed available `DELIVERY_DELAY_H` hours after
acquisition (24 h by default; the validation reports 7 h and 48 h too).
Ground truth for validation still uses the acquisition time: that is when the
lava was really there.

The lava ensemble is computed once over the pre-eruption terrain, starting
from the vent (the highest point of the first observed flow, 20 Sep). Each
day, its members are reweighted with the observations available
(`volscan.assimilation`). Before the eruption there is no lava forecast:
only seismicity, plus an optional "what if" scenario starting from the
centroid of the shallow seismicity, clearly labelled as such.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import assimilation as A
from .datasets import DATA, LAPALMA_2021_ONSET, load_grid_npz, load_lava_extents
from .geo import lonlat_to_utm28, utm28_to_lonlat
from .lava import LavaForecast, LavaParams, LogNormal, forecast
from .raster import rasterize_lonlat
from .seismic import Catalog, unrest
from .zones import in_zone

CASE = DATA / "lapalma2021"
CACHE = Path(__file__).resolve().parents[1] / "out" / "cache"
SEA_ENTRY_REAL = dt.datetime(2021, 9, 28, 22, 2, tzinfo=dt.timezone.utc)
SWARM_START = dt.date(2021, 9, 11)
REPLAY_END = dt.date(2021, 12, 25)
DELIVERY_DELAY_H = 24.0
WATCH_P_HIGH = 0.01          # first tier of the watch list: some ensemble member reaches the building
WATCH_POCKET = 0.2           # second tier: hemmed in by the flow field (infill score)
CAL_SMOOTH = 5.0
INFILL_SHARE = 0.3           # share of new area placed by the infill score for the upper bound             # additive smoothing of the error ratios used to calibrate the range

ENSEMBLE = LavaParams(n_paths=600, viscosity_pa_s=LogNormal(3e6, 1.5), max_length_m=LogNormal(6000, 0.5))


class LaPalma2021:
    def __init__(self, catalog: Catalog | None = None, params: LavaParams = ENSEMBLE, seed: int = 0,
                 delivery_delay_h: float = DELIVERY_DELAY_H):
        self.delay = dt.timedelta(hours=delivery_delay_h)
        self.grid = load_grid_npz(CASE / "dem_utm25.npz")
        self.obs = load_lava_extents(CASE / "lava_extents.geojson")
        self.places = json.loads((CASE / "places.json").read_text())
        self.catalog = catalog
        self.params, self.seed = params, seed
        g = self.grid
        self.valid = ~np.isnan(g.elev)
        first = rasterize_lonlat(g, self.obs[0].polygons)
        z = np.where(first, g.elev, -np.inf)
        vi, vj = np.unravel_index(int(np.argmax(z)), z.shape)
        self.vent_xy = tuple(float(v) for v in g.ij_to_xy(vi, vj))
        X, Y = g.cell_centres()
        self.dist = np.hypot(X - self.vent_xy[0], Y - self.vent_xy[1]).ravel()
        self._masks: dict[int, np.ndarray] = {}
        self.fc = self._ensemble()
        self._coast = self._coast_cells()
        self._place_cells = {p["name"]: self._cells_near(p["lon"], p["lat"], 150.0) for p in self.places["places"]}
        self._ll = {}

    # ---------- setup
    def _ensemble(self) -> LavaForecast:
        key = hashlib.sha256(json.dumps([repr(self.params), self.seed, self.vent_xy]).encode()).hexdigest()[:16]
        f = CACHE / f"lapalma2021_ensemble_{key}.npz"
        if f.exists():
            d = np.load(f, allow_pickle=False)
            n = len(d["weights"])
            return LavaForecast(self.grid, d["cell"], d["path"], d["t_h"], d["weights"], d["stop_reason"].astype(str),
                                {k[2:]: d[k] for k in d.files if k.startswith("m_")}) if n else None
        fc = forecast(self.grid, [self.vent_xy], self.params, seed=self.seed)
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(f, cell=fc.cell, path=fc.path, t_h=fc.t_h, weights=fc.weights,
                            stop_reason=fc.stop_reason.astype("U8"), **{f"m_{k}": v for k, v in fc.members.items()})
        return fc

    def _coast_cells(self):
        sea = ~self.valid
        near = np.zeros_like(sea)
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            near |= np.roll(np.roll(sea, di, 0), dj, 1)
        return np.flatnonzero((self.valid & near).ravel())

    def _cells_near(self, lon, lat, radius_m):
        x, y = lonlat_to_utm28(lon, lat)
        X, Y = self.grid.cell_centres()
        m = (np.hypot(X - float(x), Y - float(y)) <= radius_m) & self.valid
        return np.flatnonzero(m.ravel())

    def mask(self, k: int) -> np.ndarray:
        if k not in self._masks:
            self._masks[k] = rasterize_lonlat(self.grid, self.obs[k].polygons).ravel()
        return self._masks[k]

    @staticmethod
    def hours(t: dt.datetime) -> float:
        return (t - LAPALMA_2021_ONSET).total_seconds() / 3600.0

    # ---------- per-day state
    def obs_until(self, now: dt.datetime) -> list[int]:
        """Observations KNOWN at `now` (acquired and delivered)."""
        return [k for k, o in enumerate(self.obs) if o.observed_at + self.delay <= now]

    def obs_acquired_until(self, now: dt.datetime) -> list[int]:
        """Observations ACQUIRED by `now` (the ground truth of where the lava was)."""
        return [k for k, o in enumerate(self.obs) if o.observed_at <= now]

    def weights_at(self, now: dt.datetime, p: A.AssimParams = A.AssimParams()) -> np.ndarray:
        ks = self.obs_until(now)
        total = np.zeros(self.fc.n_paths)
        for k in ks:
            if k not in self._ll:
                self._ll[k] = A.log_likelihood(self.fc, self.dist, self.mask(k), self.hours(self.obs[k].observed_at), p)
            total = total + self._ll[k]
        return A.weights_from_loglik(total) if ks else np.full(self.fc.n_paths, 1.0 / self.fc.n_paths)

    def lava_state(self, now: dt.datetime) -> dict:
        if now < LAPALMA_2021_ONSET:
            return dict(phase="pre-eruptive")
        w = self.weights_at(now)
        fc = self.fc.reweighted(w)
        t_now = self.hours(now)
        ks = self.obs_until(now)
        last = self.obs[ks[-1]] if ks else None
        obs_info = None
        if ks:
            m = self.mask(ks[-1])
            reach = A.observed_reach(m, self.dist)
            prev = [k for k in ks if (last.observed_at - self.obs[k].observed_at).total_seconds() >= 40 * 3600]
            stalled = growing = None
            if prev:
                mp = self.mask(prev[-1])
                stalled = reach - A.observed_reach(mp, self.dist) < 150
                growing = m.sum() > 1.05 * mp.sum()
            obs_info = dict(observed_at=last.observed_at.isoformat(), age_h=round(t_now - self.hours(last.observed_at), 1),
                            area_ha=round(float(m.sum()) * self.grid.step ** 2 / 1e4, 1), reach_m=round(reach),
                            front_stalled=stalled, area_growing=growing, n_observations=len(ks))
        sea_t = A.member_arrival_at(self.fc, self._coast)
        sea_future = np.where(sea_t > t_now, sea_t, np.nan)
        reached_sea_obs = bool(ks) and bool(self.mask(ks[-1])[self._coast].any())
        q = A.weighted_quantiles(sea_future, w, (0.1, 0.5, 0.9))
        p_sea = float(w[np.isfinite(sea_t)].sum())
        places = []
        for name, cells in self._place_cells.items():
            if cells.size == 0:
                continue
            arr = A.member_arrival_at(self.fc, cells)
            reached = bool(ks) and bool(self.mask(ks[-1])[cells].any())
            qq = A.weighted_quantiles(np.where(arr > t_now, arr, np.nan), w, (0.1, 0.5, 0.9))
            places.append(dict(name=name, p_ever=round(float(w[np.isfinite(arr)].sum()), 3), observed_reached=reached,
                               eta_h=[None if np.isnan(v) else round(v - t_now, 1) for v in qq]))
        places.sort(key=lambda d: -d["p_ever"])
        return dict(
            phase="eruptive", hours_since_onset=round(t_now, 1), ess=round(A.ess(w), 1), n_members=self.fc.n_paths,
            observation=obs_info,
            sea=dict(p_ever=round(p_sea, 3), observed_reached=reached_sea_obs,
                     eta_h=[None if np.isnan(v) else round(v - t_now, 1) for v in q],
                     real_arrival=SEA_ENTRY_REAL.isoformat()),
            places=places,
            _fc=fc,
        )

    def seismic_state(self, now: dt.datetime) -> dict | None:
        if self.catalog is None:
            return None
        cat = self.catalog
        lp = cat.select(in_zone(cat.lat, cat.lon, "la_palma"))
        u = unrest(lp, now.timestamp())
        day0 = now.timestamp() - 86400
        d = lp.window(day0, now.timestamp())
        return dict(
            unrest_index=None if u.index is None else round(u.index, 2), components=u.components,
            rate_ratio=None if u.rate_ratio is None else round(u.rate_ratio, 1),
            shallowing_km=None if u.shallowing_km is None else round(u.shallowing_km, 1),
            last24h=dict(n=len(d), max_mag=None if not len(d) or np.all(np.isnan(d.mag)) else float(np.nanmax(d.mag)),
                         depth_median_km=None if not len(d) or np.all(np.isnan(d.depth)) else float(np.nanmedian(d.depth))),
            b_recent=None if u.recent.b is None else asdict(u.recent.b),
        )

    def overlay_png(self, fc: LavaForecast, t_h: float | None, res_deg: float = 0.00025) -> dict:
        """Probability raster reprojected to a lon/lat grid, as a PNG data URL plus Leaflet bounds."""
        p = fc.probability(t_h)
        g = self.grid
        lon0, lat0 = utm28_to_lonlat(g.west, g.south)
        lon1, lat1 = utm28_to_lonlat(g.east, g.north)
        lon_min, lon_max = float(min(lon0, utm28_to_lonlat(g.west, g.north)[0])), float(max(lon1, utm28_to_lonlat(g.east, g.south)[0]))
        lat_min, lat_max = float(min(lat0, utm28_to_lonlat(g.east, g.south)[1])), float(max(lat1, utm28_to_lonlat(g.west, g.north)[1]))
        lons = np.arange(lon_min, lon_max, res_deg) + res_deg / 2
        lats = np.arange(lat_max, lat_min, -res_deg) - res_deg / 2
        LON, LAT = np.meshgrid(lons, lats)
        X, Y = lonlat_to_utm28(LON, LAT)
        i, j = g.xy_to_ij(X, Y)
        ok = (i >= 0) & (i < g.shape[0]) & (j >= 0) & (j < g.shape[1])
        val = np.zeros(LON.shape)
        val[ok] = p[i[ok], j[ok]]
        rgba = _lava_colormap(val)
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
        return dict(png="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
                    bounds=[[lat_min, lon_min], [lat_max, lon_max]])

    def observed_geojson(self, now: dt.datetime) -> dict | None:
        ks = self.obs_until(now)
        if not ks:
            return None
        o = self.obs[ks[-1]]
        return dict(type="Feature", properties=dict(observed_at=o.observed_at.isoformat(), source="Copernicus EMS EMSR546"),
                    geometry=dict(type="MultiPolygon", coordinates=o.polygons))

    def vent_lonlat(self):
        lon, lat = utm28_to_lonlat(*self.vent_xy)
        return float(lon), float(lat)


def _lava_colormap(p: np.ndarray) -> np.ndarray:
    """0 → transparent; low → deep red, high → bright yellow. Alpha grows with probability."""
    p = np.clip(p, 0, 1)
    r = np.clip(120 + 135 * np.sqrt(p), 0, 255)
    gch = np.clip(20 + 220 * p ** 1.5, 0, 255)
    b = np.clip(10 + 40 * p ** 3, 0, 255)
    a = np.where(p > 0.005, np.clip(60 + 190 * np.sqrt(p), 0, 255), 0)
    return np.stack([r, gch, b, a], -1).astype(np.uint8)


@lru_cache(maxsize=1)
def default_replay(catalog_key: str = "") -> LaPalma2021:
    from .catalog_store import load_catalog
    return LaPalma2021(catalog=load_catalog())


def replay_days():
    d = SWARM_START
    while d <= REPLAY_END:
        yield d
        d += dt.timedelta(days=1)


# ---------------------------------------------------------------- impact, pre-eruptive scenario, validation
class ImpactReplay:
    """Impact layer over the La Palma 2021 replay (see volscan.impact)."""

    def __init__(self, base: "LaPalma2021"):
        from .impact import load_exposure
        self.r = base
        self.exp = load_exposure(base.grid, CASE / "exposure")
        self._scen = {}
        self._pocket: dict = {}
        self._raw: dict = {}

    @staticmethod
    def _public(I: dict) -> dict:
        I = dict(I)
        I.pop("building_probability", None)
        crit = [f for f in I["facilities"] if f["kind"] != "Estanque de riego"]
        ponds = [f for f in I["facilities"] if f["kind"] == "Estanque de riego"]
        I["facilities"] = crit[:25]
        I["ponds"] = dict(expected=round(sum(f["p"] for f in ponds if not f["already_lost"]), 1),
                          already_lost=sum(1 for f in ponds if f["already_lost"]))
        return I

    def growth_rates(self, now: dt.datetime, window_days: float = 6.0) -> list[float]:
        """Observed area growth rates (ha/h) between consecutive CEMS maps known at `now`, over the last few days."""
        r = self.r
        ks = r.obs_until(now)
        cell_ha = r.grid.step ** 2 / 1e4
        rec = [k for k in ks if (now - r.obs[k].observed_at).total_seconds() <= window_days * 86400]
        rates = []
        for a, b in zip(rec[:-1], rec[1:]):
            dh = (r.obs[b].observed_at - r.obs[a].observed_at).total_seconds() / 3600
            if dh >= 6:
                rates.append(max(0.0, float(r.mask(b).sum() - r.mask(a).sum()) * cell_ha / dh))
        if not rates and ks:
            rates = [float(r.mask(ks[-1]).sum()) * cell_ha / max(r.hours(r.obs[ks[-1]].observed_at), 1.0)]
        return rates

    # ---------- buildings hemmed in by the flow ("pockets")
    def pocket(self, k: int) -> np.ndarray:
        """Infill score per cell for map k (see volscan.lateral.infill_prior)."""
        from .lateral import infill_prior
        if k not in self._pocket:
            r = self.r
            self._pocket[k] = infill_prior(r.mask(k).reshape(r.grid.shape), r.valid, r.grid.step).ravel()
        return self._pocket[k]

    def watch_list(self, now: dt.datetime, horizon_h: float, fc) -> dict:
        """Two tiers of buildings still standing, for evacuation planning.

        - "alta": some ensemble member reaches it within the horizon (p >= 1 %).
        - "cercada": not in the first tier, but hemmed in by the flow field
          (infill score >= 0.2). That is where lateral growth and new lobes go.
        Their measured recall/precision over 2021 is in the validation.
        """
        r = self.r
        ks = r.obs_until(now)
        bc = self.exp.bld_cell
        okb = bc >= 0
        c = np.clip(bc, 0, None)
        alive = okb & ~(r.mask(ks[-1])[c] if ks else np.zeros(len(bc), bool))
        pm = fc.probability(r.hours(now) + horizon_h).ravel()
        high = alive & (pm[c] >= WATCH_P_HIGH)
        pocket = alive & ~high & ((self.pocket(ks[-1])[c] >= WATCH_POCKET) if ks else False)
        return dict(high=high, pocket=pocket)

    def constrained(self, now: dt.datetime, horizon_h: float, p_flat: np.ndarray, already: np.ndarray) -> dict:
        """Area-constrained expectation (low / central / high from the spread of recent growth rates).

        The area to place covers the time since the last KNOWN map, not only the
        horizon: a map known now may be a day old.
        """
        from .impact import expected_from_cells, scale_to_area
        r = self.r
        cell_ha = r.grid.step ** 2 / 1e4
        rates = self.growth_rates(now)
        ks = r.obs_until(now)
        lag_h = (now - r.obs[ks[-1]].observed_at).total_seconds() / 3600 if ks else 0.0
        span = horizon_h + lag_h
        lo, mid, hi = (min(rates) * 0.7, float(np.median(rates)), max(rates) * 1.3) if rates else (0, 0, 0)
        out = {}
        for k, rate in (("low", lo), ("central", mid), ("high", hi)):
            q = scale_to_area(p_flat, rate * span, cell_ha, already)
            out[k] = expected_from_cells(q, self.exp)
            if k == "central":
                q_mid = q
        return dict(rates_ha_h=[round(x, 2) for x in rates], map_age_h=round(lag_h, 1),
                    area_ha=dict(low=round(lo * span, 1), central=round(mid * span, 1), high=round(hi * span, 1)),
                    buildings=dict(low=round(out["low"]["buildings"]), central=round(out["central"]["buildings"]),
                                   high=round(out["high"]["buildings"])),
                    road_km=dict(low=round(out["low"]["road_km"], 1), central=round(out["central"]["road_km"], 1),
                                 high=round(out["high"]["road_km"], 1)), _q=q_mid)

    def coverage_map(self, now: dt.datetime, horizon_h: float = 72.0) -> np.ndarray | None:
        """Per-cell probability of new lava within the horizon (area-constrained, central), shape = grid."""
        r = self.r
        ks = r.obs_until(now)
        if not ks:
            return None
        fc = r.lava_state(now)["_fc"]
        return self.constrained(now, horizon_h, fc.probability(r.hours(now) + horizon_h).ravel(),
                                r.mask(ks[-1]))["_q"].reshape(r.grid.shape)

    def eruptive(self, now: dt.datetime, horizon_h: float = 72.0) -> dict:
        from .impact import impact, isolation, observed_losses
        r = self.r
        L = r.lava_state(now)
        fc = L["_fc"]
        t_now = r.hours(now)
        ks = r.obs_until(now)
        already = r.mask(ks[-1]) if ks else None
        I = impact(fc, self.exp, t_now + horizon_h, already)
        iso = isolation(fc, self.exp, t_now + horizon_h, already)
        later = now + dt.timedelta(hours=horizon_h)
        kl = r.obs_acquired_until(later)
        truth = None
        if kl and ks and kl[-1] != ks[-1] and later <= r.obs[-1].observed_at + dt.timedelta(days=1):
            t_obs = observed_losses(self.exp, r.mask(kl[-1]))
            base = I["already_lost"]
            truth = dict(at=r.obs[kl[-1]].observed_at.isoformat(),
                         new_buildings=t_obs["buildings"] - base["buildings"],
                         new_road_km=round(t_obs["road_km"] - base["road_km"], 2))
        C, pts, watch = None, [], None
        if ks:
            C = self.constrained(now, horizon_h, fc.probability(t_now + horizon_h).ravel(), already)
            q = C.pop("_q")
            if horizon_h == 72.0:
                cal = self.calibrated(now, C["buildings"]["central"])
                hi_inf = self.infill_high(now, horizon_h, fc, already)
                if cal:
                    C["buildings"].update(low=cal["low"], high=max(cal["high"], hi_inf))
                    C["interval"] = dict(cal, infill_high=hi_inf)
                else:
                    C["buildings"]["high"] = max(C["buildings"]["high"], hi_inf)
            bc = self.exp.bld_cell
            qb = np.where(bc >= 0, q[np.clip(bc, 0, None)], 0.0)
            pts = [(float(x), float(y), round(float(v), 3)) for (x, y), v in zip(self.exp.bld_xy, qb) if v >= 0.02]
            W = self.watch_list(now, horizon_h, fc)
            watch = dict(high=int(W["high"].sum()), pocket=int(W["pocket"].sum()),
                         pocket_xy=[(float(x), float(y)) for (x, y), f in zip(self.exp.bld_xy, W["pocket"]) if f])
        return dict(phase="eruptive", **self._public(I), constrained=C, isolation=iso[:15], truth_after=truth,
                    buildings_at_risk_xy=pts, watch=watch, map_delay_h=r.delay.total_seconds() / 3600,
                    method="Dónde: conjunto de coladas desde la boca, reponderado con lo observado. Cuánto: crecimiento de "
                           "área de los mapas de Copernicus ya entregados, contando desde la fecha del último mapa. Rango: "
                           "calibrado con el error real de los pronósticos anteriores cuya verdad ya se conoce. Aislamiento: "
                           "miembros del conjunto sobre la red de OSM. Edificios cercados: rodeados por la colada, donde va el "
                           "crecimiento lateral.")

    def scenario(self, now: dt.datetime, n_paths: int = 500) -> dict | None:
        """Pre-eruptive: vents drawn from the shallow seismicity of the last 72 h. Hours count from the (unknown) opening."""
        from .impact import impact, isolation
        from .lava import LavaParams, LogNormal, forecast
        key = now.date().isoformat()
        if key in self._scen:
            return self._scen[key]
        cat = self.r.catalog
        if cat is None:
            return None
        g = self.r.grid
        t1, t0 = now.timestamp(), now.timestamp() - 72 * 3600
        m = (cat.t >= t0) & (cat.t < t1) & in_zone(cat.lat, cat.lon, "la_palma") & ~np.isnan(cat.depth)
        if m.sum() < 30:
            self._scen[key] = None
            return None
        depth = cat.depth[m]
        shallow = depth <= np.percentile(depth, 30)
        x, y = lonlat_to_utm28(cat.lon[m][shallow], cat.lat[m][shallow])
        i, j = g.xy_to_ij(x, y)
        ok = (i >= 0) & (i < g.shape[0]) & (j >= 0) & (j < g.shape[1])
        ok[ok] &= ~np.isnan(g.elev[i[ok], j[ok]])
        if ok.sum() < 10:
            self._scen[key] = None
            return None
        vents = [(float(a), float(b), 1.0) for a, b in zip(x[ok], y[ok])]
        params = LavaParams(n_paths=n_paths, viscosity_pa_s=LogNormal(3e6, 1.5), max_length_m=LogNormal(6000, 0.5),
                            vent_sigma_m=1000.0)
        fc = forecast(g, vents, params, seed=11)
        I = impact(fc, self.exp, 24 * 30)
        iso = isolation(fc, self.exp, 24 * 30)
        p = fc.probability()
        from .textures import lava_overlay_rgba, png_data_url
        rv = self.r.vent_xy
        d_real = float(np.min(np.hypot(x[ok] - rv[0], y[ok] - rv[1])))
        out = dict(phase="pre-eruptive", n_vent_events=int(ok.sum()), shallow_depth_max_km=round(float(np.percentile(depth, 30)), 1),
                   vent_centroid_xy=[float(np.median(x[ok])), float(np.median(y[ok]))],
                   nearest_candidate_to_real_vent_km=round(d_real / 1000, 2),
                   **self._public(I), isolation=iso[:15],
                   places=[dict(name=pl["name"], p=round(float(fc.probability()[np.unravel_index(pl["cell"], g.shape)]), 3))
                           for pl in self.exp.places if pl["cell"] >= 0],
                   overlay=dict(png=png_data_url(lava_overlay_rgba(p, None), "RGBA"), west=g.west, north=g.north, step=g.step,
                                rows=g.shape[0], cols=g.shape[1], horizon_h=None,
                                legend="Escenario: colada desde las bocas probables (sismicidad somera de las últimas 72 h)"),
                   note="Escenario anticipado: no se sabe dónde abrirá la boca. Se lanzan coladas desde donde se concentra "
                        "la sismicidad más somera (con 1 km de incertidumbre). Las horas cuentan desde una apertura hipotética.")
        out["places"] = sorted([q for q in out["places"] if q["p"] >= 0.01], key=lambda q: -q["p"])[:15]
        self._scen[key] = out
        return out

    def infill_high(self, now: dt.datetime, horizon_h: float, fc, already: np.ndarray) -> int:
        """Upper bound if part of the new area goes to the ground hemmed in by the flow (lateral infill).

        The count itself stays on the main ensemble (mixing made it worse, see
        volscan.lateral); but the P90 must cover the days when the growth fills
        a dense pocket, as on 9–13 Oct 2021. It takes the high growth rate with
        30 % of the new area placed by the infill score.
        """
        from .lateral import infill_prior  # noqa: F401  (documentation pointer)
        r = self.r
        pm = fc.probability(r.hours(now) + horizon_h).ravel()
        pk = self.pocket(r.obs_until(now)[-1])
        a = pm / pm.sum() if pm.sum() > 0 else pm
        b = pk / pk.sum() if pk.sum() > 0 else pk
        return int(self.constrained(now, horizon_h, (1 - INFILL_SHARE) * a + INFILL_SHARE * b, already)["buildings"]["high"])

    # ---------- validation and calibration
    def raw_row(self, d: dt.date, horizons=(24.0, 72.0)) -> dict | None:
        """Forecast made at the end of day d (central + rate range), the truth, and when that truth became known."""
        from .impact import observed_losses
        if d in self._raw:
            return self._raw[d]
        r = self.r
        now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
        ks = r.obs_until(now)
        row = None
        if ks and now >= LAPALMA_2021_ONSET:
            fc = r.lava_state(now)["_fc"]
            base = observed_losses(self.exp, r.mask(ks[-1]))
            row = dict(date=d.isoformat(), lost_buildings=base["buildings"], lost_road_km=base["road_km"],
                       map_age_h=round((now - r.obs[ks[-1]].observed_at).total_seconds() / 3600, 1))
            for h in horizons:
                later = now + dt.timedelta(hours=h)
                kl = r.obs_acquired_until(later)
                C = self.constrained(now, h, fc.probability(r.hours(now) + h).ravel(), r.mask(ks[-1]))
                b = C["buildings"]
                row[f"pred_{int(h)}"] = dict(expected=b["central"], p10_p90=[b["low"], b["high"]])
                if kl[-1] != ks[-1]:
                    newm = r.mask(kl[-1])
                    row[f"obs_{int(h)}"] = observed_losses(self.exp, newm)["buildings"] - base["buildings"]
                    row[f"_truth_known_{int(h)}"] = (r.obs[kl[-1]].observed_at + r.delay).isoformat()
                    if h == 72.0:
                        row["_infill_high_72"] = self.infill_high(now, h, fc, r.mask(ks[-1]))
                        W = self.watch_list(now, h, fc)
                        c = np.clip(self.exp.bld_cell, 0, None)
                        lost = (self.exp.bld_cell >= 0) & newm[c] & ~r.mask(ks[-1])[c]
                        row["watch"] = dict(high=int(W["high"].sum()), high_hit=int((W["high"] & lost).sum()),
                                            pocket=int(W["pocket"].sum()), pocket_hit=int((W["pocket"] & lost).sum()),
                                            lost=int(lost.sum()))
        self._raw[d] = row
        return row

    def calibrated(self, now: dt.datetime, central: float) -> dict | None:
        """P10–P90 from the real errors of earlier 72 h forecasts whose truth is already known at `now`.

        Ratios (obs + 5) / (pred + 5) of every completed forecast; their 10th and
        90th percentiles stretch the current central value. It needs at least 5
        completed forecasts; before that, the range comes from the spread of
        recent growth rates only.
        """
        ratios = []
        d = LAPALMA_2021_ONSET.date()
        while d < now.date():
            row = self.raw_row(d)
            if row and "obs_72" in row and dt.datetime.fromisoformat(row["_truth_known_72"]) <= now:
                ratios.append((row["obs_72"] + CAL_SMOOTH) / (row["pred_72"]["expected"] + CAL_SMOOTH))
            d += dt.timedelta(days=1)
        if len(ratios) < 5:
            return None
        lo, hi = np.quantile(ratios, [0.1, 0.9])
        return dict(low=max(0, round((central + CAL_SMOOTH) * lo - CAL_SMOOTH)), high=round((central + CAL_SMOOTH) * hi - CAL_SMOOTH),
                    n_past=len(ratios), ratio_p10_p90=[round(float(lo), 2), round(float(hi), 2)])

    def validation(self) -> list[dict]:
        """Every day of the eruption: the 72 h forecast VolScan would have issued, against what CEMS later mapped."""
        out = []
        d = LAPALMA_2021_ONSET.date()
        while d <= dt.date(2021, 12, 13):
            row = self.raw_row(d)
            if row:
                hi_inf = row.get("_infill_high_72")
                row = {k: v for k, v in row.items() if not k.startswith("_")}
                now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
                cal = self.calibrated(now, row["pred_72"]["expected"])
                lo, hi = (cal["low"], cal["high"]) if cal else row["pred_72"]["p10_p90"]
                if hi_inf is not None:
                    hi = max(hi, hi_inf)
                row["pred_72"] = dict(row["pred_72"], rate_range=row["pred_72"]["p10_p90"], p10_p90=[lo, hi],
                                      calibrated=bool(cal), infill_high=hi_inf)
                out.append(row)
            d += dt.timedelta(days=1)
        return out


def validation_summary(rows: list[dict]) -> dict:
    within = [r for r in rows if "obs_72" in r]
    inside = lambda r: r["pred_72"]["p10_p90"][0] <= r["obs_72"] <= r["pred_72"]["p10_p90"][1]
    first10 = [r for r in within if r["date"] <= "2021-09-29"]
    pred = sum(r["pred_72"]["expected"] for r in within)
    obs = sum(r["obs_72"] for r in within)
    err = [abs(r["pred_72"]["expected"] - r["obs_72"]) for r in within]
    return dict(days=len(within), within_p10_p90_72h=sum(1 for r in within if inside(r)),
                total_pred_72=round(pred), total_obs_72=obs, bias_pct=round(100 * (pred - obs) / obs, 1) if obs else None,
                mae_72=round(float(np.mean(err)), 1) if err else None,
                first_10_days=dict(days=len(first10), within=sum(1 for r in first10 if inside(r))),
                watch=_watch_summary(within))


def _watch_summary(rows: list[dict]) -> dict | None:
    w = [r["watch"] for r in rows if r.get("watch")]
    if not w:
        return None
    lost = sum(x["lost"] for x in w)
    hh, hp = sum(x["high_hit"] for x in w), sum(x["pocket_hit"] for x in w)
    nh, npk = sum(x["high"] for x in w), sum(x["pocket"] for x in w)
    return dict(lost=lost, high=dict(recall=round(hh / lost, 3) if lost else None, precision=round(hh / nh, 3) if nh else None,
                                     median_flagged=float(np.median([x["high"] for x in w]))),
                with_pocket=dict(recall=round((hh + hp) / lost, 3) if lost else None,
                                 precision=round((hh + hp) / (nh + npk), 3) if nh + npk else None,
                                 median_flagged=float(np.median([x["high"] + x["pocket"] for x in w]))))


def validation_payload(ir: ImpactReplay, sensitivity: dict | None = None) -> dict:
    rows = ir.validation()
    return dict(rows=rows, summary=validation_summary(rows), map_delay_h=ir.r.delay.total_seconds() / 3600,
                delay_sensitivity=sensitivity,
                truth="Copernicus EMS EMSR546: edificios dentro de la colada observada (inventario CEMS, 2.988 destruidos al final)",
                method="Cada día a las 23:59 UTC, con los mapas de Copernicus ya entregados (se supone que llegan 24 h después "
                       "de la imagen), VolScan pronostica los edificios nuevos alcanzados en 72 h. Se compara con el mapa "
                       "adquirido 72 h después. El rango P10–P90 se calibra solo con los errores de pronósticos anteriores "
                       "cuya verdad ya se conocía ese día.")
