"""Tenerife: prepared impact scenarios for the volcanic systems with historical eruptions, plus one from today's seismicity.

WHY PREPARED SCENARIOS
----------------------
Tenerife has had seismic-volcanic activity above normal since February 2026
(IGN), and on 22 Oct 2026 the Cabildo ran the VULCANEX drill. Nobody knows
where a vent would open, but the island's history narrows it down: every
historical eruption came from the two rifts or from the flanks of
Teide–Pico Viejo. For each of those, VolScan runs the same lava ensemble and
impact engine validated on La Palma 2021 and answers the planning questions:
which neighbourhoods, roads and services the lava would reach, with what
probability, how fast, and which places would be cut off.

The vents are the historical vents (OpenStreetMap peak/volcano positions)
with 700–800 m of uncertainty. The "current seismicity" scenario puts vents
over the shallowest 30 % of the epicentres of the last 90 days, like the
La Palma pre-eruptive scenario.

LIMITS, IN PLAIN WORDS
----------------------
- The lava parameters are those of the basaltic La Palma ensemble. Basaltic
  rift eruptions (1705, 1706, 1909) fit. Phonolitic eruptions from Teide or
  Pico Viejo would make shorter, thicker flows, and an explosive phase this
  model does not cover.
- Exposure is OpenStreetMap as of 27 Oct 2026: ~100,000 building outlines.
  Coverage varies by municipality, so building counts are a lower bound.
- A scenario is a planning tool. It does not say that an eruption is likely,
  nor where it would happen. The official assessment belongs to PEVOLCA.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .datasets import DATA, load_grid_npz
from .geo import lonlat_to_utm28, utm28_to_lonlat
from .lava import LavaParams, LogNormal, forecast

CASE = DATA / "tenerife"
CACHE = Path(__file__).resolve().parents[1] / "out" / "cache"
EXPOSURE_TAG = "20261027"
HORIZON_H = 24 * 30
HUBS = ("Puerto de la Cruz", "Los Cristianos", "Güímar", "La Orotava", "Adeje")

SCENARIOS = [
    dict(key="dorsal_noroeste", name="Dorsal noroeste", history="Garachico 1706 (Arenas Negras) · Chinyero 1909",
         vents=[(-16.7645, 28.3161, "Arenas Negras (1706)"), (-16.7571, 28.2949, "Chinyero (1909)"),
                (-16.7916, 28.2937, "Montaña Bilma")], sigma_m=700.0),
    dict(key="pico_viejo", name="Flanco oeste de Pico Viejo", history="Narices del Teide / Chahorra 1798",
         vents=[(-16.6768, 28.2548, "Montaña Chahorra (1798)"), (-16.7000, 28.2657, "Montaña Reventada")], sigma_m=700.0),
    dict(key="teide_norte", name="Flanco norte del Teide", history="Sin erupción histórica; drena hacia Icod y La Orotava",
         vents=[(-16.6064, 28.3063, "Montaña Negra (norte del Teide)"), (-16.6423, 28.2900, "Ladera norte del Teide")],
         sigma_m=800.0),
    dict(key="dorsal_noreste", name="Dorsal noreste", history="Sietefuentes, Fasnia y Arafo 1704–1705",
         vents=[(-16.5132, 28.2845, "Volcanes de Fasnia (1705)"), (-16.4621, 28.3402, "Volcán de Arafo (1705)"),
                (-16.5295, 28.2707, "Montaña Negra o del Volcán")], sigma_m=700.0),
]
SEISMIC_KEY = "sismicidad_actual"

PARAMS = LavaParams(n_paths=500, viscosity_pa_s=LogNormal(3e6, 1.5), max_length_m=LogNormal(6000, 0.5))


@lru_cache(maxsize=1)
def grid():
    return load_grid_npz(CASE / "dem_utm25.npz")


@lru_cache(maxsize=1)
def exposure():
    from .impact import load_exposure_osm
    return load_exposure_osm(grid(), CASE / "exposure", EXPOSURE_TAG, hubs=HUBS)


def seismic_vents(cat, at_ts: float, days: int = 90, share: float = 0.3):
    """Vents over the shallowest `share` of the Tenerife epicentres of the last `days` (inside the lava grid)."""
    from .catalog_store import zone_catalog
    zc = zone_catalog(cat, "tenerife").window(at_ts - days * 86400, at_ts)
    ok = ~np.isnan(zc.depth)
    if ok.sum() < 20:
        return [], None
    d = zc.depth[ok]
    cut = float(np.percentile(d, share * 100))
    sel = d <= cut
    x, y = lonlat_to_utm28(zc.lon[ok][sel], zc.lat[ok][sel])
    g = grid()
    i, j = g.xy_to_ij(x, y)
    inside = (i >= 0) & (i < g.shape[0]) & (j >= 0) & (j < g.shape[1])
    inside[inside] &= ~np.isnan(g.elev[i[inside], j[inside]])
    return [(float(a), float(b)) for a, b in zip(x[inside], y[inside])], dict(n_events=int(ok.sum()), depth_cut_km=round(cut, 1),
                                                                               n_vents=int(inside.sum()), days=days)


def run(spec: dict, vents_xy: list, seed: int = 21) -> dict:
    """Ensemble + impact for one scenario (cached on disk by its inputs)."""
    from .impact import impact, isolation
    from .textures import lava_overlay_rgba, png_data_url
    key = hashlib.sha256(json.dumps([spec["key"], vents_xy, spec.get("sigma_m"), repr(PARAMS), seed, EXPOSURE_TAG],
                                    default=str).encode()).hexdigest()[:16]
    f = CACHE / f"tenerife_{spec['key']}_{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    g, exp = grid(), exposure()
    params = LavaParams(**{**PARAMS.__dict__, "vent_sigma_m": spec.get("sigma_m", 1000.0)})
    fc = forecast(g, vents_xy, params, seed=seed)
    I = impact(fc, exp, HORIZON_H)
    iso = isolation(fc, exp, HORIZON_H)
    p = fc.probability()
    # overlay at 50 m (max-pooled) to keep the page light
    r2, c2 = g.shape[0] // 2 * 2, g.shape[1] // 2 * 2
    p2 = p[:r2, :c2].reshape(r2 // 2, 2, c2 // 2, 2).max(axis=(1, 3))
    places = []
    for pl in exp.places:
        if pl["cell"] < 0:
            continue
        i, j = np.unravel_index(pl["cell"], g.shape)
        pv = float(p[i, j])
        if pv >= 0.01:
            places.append(dict(name=pl["name"], kind=pl["kind"], p=round(pv, 3), x=pl["x"], y=pl["y"]))
    places.sort(key=lambda d: -d["p"])
    bp = I.pop("building_probability")
    pts = [(float(x), float(y), round(float(v), 3)) for (x, y), v in zip(exp.bld_xy, bp) if v >= 0.05]
    stop = fc.stop_fractions()
    out = dict(
        key=spec["key"], name=spec["name"], history=spec.get("history"), horizon_h=HORIZON_H,
        vents=[dict(lonlat=[float(v) for v in utm28_to_lonlat(x, y)], xy=[x, y]) for x, y in vents_xy[:60]],
        n_paths=fc.n_paths, reach_sea=round(stop.get("nodata", 0.0), 3),
        buildings=I["buildings"], road_km=I["road_km"], facilities=[f for f in I["facilities"] if f["kind"] != "Estanque de riego"][:25],
        ponds=round(sum(f["p"] for f in I["facilities"] if f["kind"] == "Estanque de riego"), 1),
        places=places[:20], isolation=iso[:15], buildings_at_risk_xy=pts[:6000], n_buildings_exposed=int((bp >= 0.05).sum()),
        overlay=dict(png=png_data_url(lava_overlay_rgba(p2, None), "RGBA"), west=g.west, north=g.north, step=g.step * 2,
                     rows=p2.shape[0], cols=p2.shape[1], horizon_h=None,
                     legend=f"Escenario {spec['name']}: probabilidad de que la colada alcance cada punto (30 días)"),
        exposure_note="Edificios: OpenStreetMap a 27 oct 2026 (~100.000 contornos; la cobertura varía por municipio, es una cota inferior).",
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def scenario(key: str, cat=None, at_ts: float | None = None) -> dict | None:
    if key == SEISMIC_KEY:
        if cat is None:
            return None
        at_ts = at_ts or float(cat.t.max())
        vents, info = seismic_vents(cat, at_ts)
        if len(vents) < 5:
            return dict(key=key, name="Sismicidad de los últimos 90 días", unavailable=True,
                        note="Pocos sismos localizados en los últimos 90 días para situar bocas.")
        rng = np.random.default_rng(0)
        if len(vents) > 300:
            vents = [vents[k] for k in sorted(rng.choice(len(vents), 300, replace=False))]
        spec = dict(key=key, name="Sismicidad de los últimos 90 días",
                    history=f"Bocas sobre el 30 % más somero de {info['n_events']} sismos (≤ {info['depth_cut_km']} km)",
                    sigma_m=1500.0)
        out = run(spec, vents)
        out["seismic"] = info
        out["note"] = ("Hipótesis, no pronóstico: la sismicidad de Tenerife está a 6–20 km bajo Las Cañadas y no marca dónde "
                       "abriría una boca. Sirve para ver qué quedaría expuesto si abriera sobre ella.")
        return out
    spec = next((s for s in SCENARIOS if s["key"] == key), None)
    if spec is None:
        return None
    vents = []
    for lon, lat, _ in spec["vents"]:
        x, y = lonlat_to_utm28(lon, lat)
        vents.append((float(x), float(y)))
    out = run(spec, vents)
    out["vent_names"] = [n for _, _, n in spec["vents"]]
    return out


def catalogue() -> list[dict]:
    return [dict(key=s["key"], name=s["name"], history=s["history"]) for s in SCENARIOS] + \
        [dict(key=SEISMIC_KEY, name="Sismicidad de los últimos 90 días", history="Hipótesis a partir del catálogo IGN")]
