"""La Palma 2021 replay: what VolScan would have known, day by day.

For each day we use ONLY information available by the end of that day:
seismicity up to that moment, and CEMS observations acquired up to that
moment. (There's a caveat: CEMS published some maps hours after acquiring
them. We use the acquisition time and say so in the interface.)

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
from .zones import BY_KEY

CASE = DATA / "lapalma2021"
CACHE = Path(__file__).resolve().parents[1] / "out" / "cache"
SEA_ENTRY_REAL = dt.datetime(2021, 9, 28, 22, 2, tzinfo=dt.timezone.utc)
SWARM_START = dt.date(2021, 9, 11)
REPLAY_END = dt.date(2021, 12, 25)

ENSEMBLE = LavaParams(n_paths=600, viscosity_pa_s=LogNormal(3e6, 1.5), max_length_m=LogNormal(6000, 0.5))


class LaPalma2021:
    def __init__(self, catalog: Catalog | None = None, params: LavaParams = ENSEMBLE, seed: int = 0):
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
        z = BY_KEY["la_palma"]
        cat = self.catalog
        inz = (cat.lat >= z.lat_min) & (cat.lat <= z.lat_max) & (cat.lon >= z.lon_min) & (cat.lon <= z.lon_max)
        lp = cat.select(inz)
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
        """Observed area growth rates (ha/h) between consecutive CEMS maps of the last few days."""
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

    def constrained(self, now: dt.datetime, horizon_h: float, p_flat: np.ndarray, already: np.ndarray) -> dict:
        """Area-constrained expectation (low / central / high from the spread of recent growth rates)."""
        from .impact import expected_from_cells, scale_to_area
        cell_ha = self.r.grid.step ** 2 / 1e4
        rates = self.growth_rates(now)
        lo, mid, hi = (min(rates) * 0.7, float(np.median(rates)), max(rates) * 1.3) if rates else (0, 0, 0)
        out = {}
        for k, rate in (("low", lo), ("central", mid), ("high", hi)):
            q = scale_to_area(p_flat, rate * horizon_h, cell_ha, already)
            out[k] = expected_from_cells(q, self.exp)
            if k == "central":
                q_mid = q
        return dict(rates_ha_h=[round(x, 2) for x in rates], area_ha=dict(low=round(lo * horizon_h, 1), central=round(mid * horizon_h, 1),
                    high=round(hi * horizon_h, 1)), buildings=dict(low=round(out["low"]["buildings"]), central=round(out["central"]["buildings"]),
                    high=round(out["high"]["buildings"])), road_km=dict(low=round(out["low"]["road_km"], 1),
                    central=round(out["central"]["road_km"], 1), high=round(out["high"]["road_km"], 1)), _q=q_mid)

    def eruptive(self, now: dt.datetime, horizon_h: float = 72.0) -> dict:
        from .impact import impact, isolation, observed_losses
        r = self.r
        L = r.lava_state(now)
        fc = L["_fc"]
        t_now = r.hours(now)
        ks = r.obs_until(now)
        already = r.mask(ks[-1]) if ks else None
        I = impact(fc, self.exp, t_now + horizon_h, already)
        bp = I["building_probability"]
        iso = isolation(fc, self.exp, t_now + horizon_h, already)
        later = now + dt.timedelta(hours=horizon_h)
        kl = r.obs_until(later)
        truth = None
        if kl and kl[-1] != (ks[-1] if ks else None) and later <= r.obs[-1].observed_at + dt.timedelta(days=1):
            t_obs = observed_losses(self.exp, r.mask(kl[-1]))
            base = I["already_lost"]
            truth = dict(at=r.obs[kl[-1]].observed_at.isoformat(),
                         new_buildings=t_obs["buildings"] - base["buildings"],
                         new_road_km=round(t_obs["road_km"] - base["road_km"], 2))
        C = self.constrained(now, horizon_h, fc.probability(t_now + horizon_h).ravel(), already)
        q = C.pop("_q")
        bc = self.exp.bld_cell
        qb = np.where(bc >= 0, q[np.clip(bc, 0, None)], 0.0)
        pts = [(float(x), float(y), round(float(v), 3)) for (x, y), v in zip(self.exp.bld_xy, qb) if v >= 0.02]
        return dict(phase="eruptive", **self._public(I), constrained=C, isolation=iso[:15], truth_after=truth,
                    buildings_at_risk_xy=pts,
                    method="Dónde: conjunto de coladas reponderado con lo observado. Cuánto: crecimiento de área observado por "
                           "Copernicus en los últimos días (bajo/central/alto). Aislamiento: miembros del conjunto sobre la red de OSM.")

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
        z = BY_KEY["la_palma"]
        m = (cat.t >= t0) & (cat.t < t1) & (cat.lat >= z.lat_min) & (cat.lat <= z.lat_max) & \
            (cat.lon >= z.lon_min) & (cat.lon <= z.lon_max) & ~np.isnan(cat.depth)
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

    def validation(self, horizons=(24.0, 72.0)) -> list[dict]:
        """Every day of the eruption: forecast at end of day for +h vs what CEMS observed later."""
        from .impact import observed_losses
        r = self.r
        out = []
        d = LAPALMA_2021_ONSET.date()
        while d <= dt.date(2021, 12, 13):
            now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
            ks = r.obs_until(now)
            if ks:
                L = r.lava_state(now)
                fc = L["_fc"]
                base = observed_losses(self.exp, r.mask(ks[-1]))
                row = dict(date=d.isoformat(), lost_buildings=base["buildings"], lost_road_km=base["road_km"])
                for h in horizons:
                    later = now + dt.timedelta(hours=h)
                    kl = r.obs_until(later)
                    C = self.constrained(now, h, fc.probability(r.hours(now) + h).ravel(), r.mask(ks[-1]))
                    b = C["buildings"]
                    row[f"pred_{int(h)}"] = dict(expected=b["central"], p10_p90=[b["low"], b["high"]])
                    if kl[-1] != ks[-1]:
                        row[f"obs_{int(h)}"] = observed_losses(self.exp, r.mask(kl[-1]))["buildings"] - base["buildings"]
                out.append(row)
            d += dt.timedelta(days=1)
        return out
