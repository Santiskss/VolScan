"""VolScan HTTP API (FastAPI) + serving the built web app.

Run:  uvicorn volscan.api.app:app --port 8200
"""
from __future__ import annotations

import datetime as dt
import json
import math
import threading
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__
from .. import catalog_store as store
from ..ai import llm, rag
from ..datasets import DATA, LAPALMA_2021_ONSET, load_grid_npz
from ..geo import lonlat_to_utm28
from ..seismic import DAY, Catalog, unrest
from ..textures import heights_b64, lava_overlay_rgba, png_data_url, relief_rgb, upsample
from ..tides import (SEMIDIURNAL_S, SPRING_NEAP_S, TidalClock, alignment_shift_test, decluster,
                     lunar_elongation, schuster, tidal_phase)
from ..zones import BY_KEY, ZONES

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "dist"
CACHE = ROOT / "out" / "cache"

app = FastAPI(title="VolScan", version=__version__)

# ------------------------------------------------------------------ users, roles, audit trail
from .. import security as sec  # noqa: E402

PUBLIC = {"/api/auth/config", "/api/login"}
NOT_AUDITED = {"/api/status", "/api/login"}


@app.middleware("http")
async def _auth_and_audit(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") and not path.startswith("/ogc"):
        return await call_next(request)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip() or None
    user = sec.user_for(token)
    if user is None and path not in PUBLIC:
        sec.audit(dict(user=None, role=None, method=request.method, path=path, query=str(request.url.query), status=401,
                       ip=request.client.host if request.client else None))
        return JSONResponse(dict(detail="inicia sesión"), status_code=401)
    request.state.user = user
    resp = await call_next(request)
    if path not in NOT_AUDITED:
        sec.audit(dict(user=user["name"] if user else None, role=user["role"] if user else None, method=request.method,
                       path=path, query=str(request.url.query), status=resp.status_code,
                       ip=request.client.host if request.client else None))
    return resp


def need(request: Request, role: str):
    u = getattr(request.state, "user", None)
    if not u or not sec.role_at_least(u["role"], role):
        raise HTTPException(403, f"necesitas el rol «{role}»")
    return u


class LoginReq(BaseModel):
    name: str
    password: str


@app.get("/api/auth/config")
def auth_config(request: Request):
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip() or None
    return J(dict(enabled=sec.auth_enabled(), user=sec.user_for(token), roles=list(sec.ROLES)))


@app.post("/api/login")
def auth_login(req: LoginReq, request: Request):
    token = sec.login(req.name, req.password)
    sec.audit(dict(user=req.name, role=None, method="POST", path="/api/login", query="", status=200 if token else 401,
                   event="login_ok" if token else "login_failed", ip=request.client.host if request.client else None))
    if not token:
        time.sleep(1.0)
        raise HTTPException(401, "usuario o contraseña incorrectos")
    return J(dict(token=token, user=sec.user_for(token)))


@app.post("/api/logout")
def auth_logout(request: Request):
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    sec.logout(token)
    return J(dict(ok=True))


@app.get("/api/audit")
def audit_trail(request: Request, limit: int = 200):
    need(request, "admin")
    return J(dict(entries=sec.read_audit(min(limit, 2000)), chain=sec.verify_audit(), auth_enabled=sec.auth_enabled()))


def _clean(o):
    """JSON-safe: NaN/inf → None, numpy → python."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def J(o):
    return JSONResponse(_clean(o))


# ------------------------------------------------------------------ status
_llm_status = dict(at=0.0, value=None)


_auto = dict(running=False)
AUTO_REFRESH_S = 15 * 60


def _auto_refresh():
    """Keep the live catalogue current without anyone pressing a button (background thread, throttled)."""
    if _auto["running"] or time.time() - (store.status()["refreshed_at"] or 0) < AUTO_REFRESH_S:
        return

    def run():
        try:
            store.refresh_live(min_interval_s=AUTO_REFRESH_S)
        finally:
            _auto["running"] = False
    _auto["running"] = True
    threading.Thread(target=run, daemon=True).start()


@app.get("/api/status")
def status():
    from ..application import get_container
    c = get_container()
    if time.time() - _llm_status["at"] > 60:
        _llm_status["value"] = c.llm.status()
        _llm_status["at"] = time.time()
    store.load_events()
    _auto_refresh()
    return J(dict(version=__version__, llm=_llm_status["value"], vision=c.segmentation.status(),
                  catalog=store.status(), now=dt.datetime.now(dt.timezone.utc).isoformat()))


# ------------------------------------------------------------------ terrain
@lru_cache(maxsize=4)
def _terrain(name: str, texture_k: int):
    files = {"lapalma": DATA / "canarias" / "terrain_lapalma_100m.npz",
             "tenerife": DATA / "canarias" / "terrain_tenerife_100m.npz",
             "archipelago": DATA / "canarias" / "terrain_archipelago_500m.npz"}
    if name not in files:
        raise HTTPException(404, "terreno desconocido")
    cf = CACHE / f"terrain_{name}_k{texture_k}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass
    g = load_grid_npz(files[name])
    zt = upsample(g.elev, texture_k) if texture_k > 1 else g.elev
    tex = relief_rgb(zt, g.step / texture_k, zmax=2200.0 if name == 'archipelago' else None,
                     sea=(203, 211, 214) if name == 'archipelago' else (214, 219, 221))
    res = dict(name=name, crs="EPSG:4083", west=g.west, north=g.north, step=g.step, rows=g.shape[0], cols=g.shape[1],
               heights_i16_b64=heights_b64(g.elev), nodata=-32768, texture=png_data_url(tex, "RGB"),
               max_elev=float(np.nanmax(g.elev)),
               attribution="Copernicus DEM GLO-30 © DLR/Airbus, provided under COPERNICUS by the EU and ESA")
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(res))
    except Exception:
        pass
    return res


@lru_cache(maxsize=4)
def _terrain_bytes(name: str, texture_k: int) -> bytes:
    cf = CACHE / f"terrain_{name}_k{texture_k}.json"
    if cf.exists():
        try:
            return cf.read_bytes()
        except Exception:
            pass
    return json.dumps(_terrain(name, texture_k)).encode("utf-8")


@app.get("/api/terrain/{name}")
def terrain(name: str):
    if name not in ("lapalma", "tenerife", "archipelago"):
        raise HTTPException(404, "terreno desconocido")
    return Response(content=_terrain_bytes(name, 2), media_type="application/json")


# ------------------------------------------------------------------ Tenerife scenarios
@app.get("/api/tenerife/scenarios")
def tf_scenarios():
    from ..tenerife import catalogue
    return J(dict(scenarios=catalogue(),
                  note="Escenarios de planificación con el mismo motor validado en La Palma 2021. No indican que una erupción sea "
                       "probable ni dónde ocurriría. La valoración oficial corresponde al PEVOLCA."))


_tf_lock = threading.Lock()


@lru_cache(maxsize=16)
def _tf_scenario_bytes(key: str, n_cat: int) -> bytes | None:
    from ..tenerife import scenario
    with _tf_lock:
        out = scenario(key, _catalog())
    if out is None:
        return None
    return json.dumps(_clean(out)).encode("utf-8")


@app.get("/api/tenerife/scenario/{key}")
def tf_scenario(key: str):
    n_cat = len(_catalog()) if key == "sismicidad_actual" else 0
    b = _tf_scenario_bytes(key, n_cat)
    if b is None:
        raise HTTPException(404, "escenario desconocido")
    return Response(content=b, media_type="application/json")


# ------------------------------------------------------------------ Canarias live
def _catalog() -> Catalog:
    return store.load_catalog()


def _daily_counts(cat: Catalog, end: float, days: int):
    edges = end - DAY * np.arange(days, -1, -1)
    c, _ = np.histogram(cat.t, bins=edges)
    return c.tolist()


_cal_lock = threading.Lock()


def _calibration() -> dict:
    """Track record of the unrest index, 2011 → today (cached on disk, rebuilt weekly)."""
    from ..calibration import load_or_build
    with _cal_lock:
        cat = _catalog()
        return load_or_build(CACHE / "unrest_calibration.json", lambda: {z.key: store.zone_catalog(cat, z.key) for z in ZONES},
                             float(cat.t.max()) if len(cat) else time.time())


@app.get("/api/canarias/calibration")
def canarias_calibration(zone: str | None = None):
    c = _calibration()
    out = {k: v for k, v in c.items() if k != "series"}
    if zone:
        out["series"] = c["series"].get(zone, [])
    return J(out)


@app.get("/api/canarias/indicators")
def canarias_indicators(zone: str = "tenerife", days: int = 120):
    """Deformation (GNSS) for one zone and the archipelago SO2 series, next to the seismic index."""
    from .. import deformation as D
    today = dt.datetime.now(dt.timezone.utc).date()
    return J(dict(zone=zone, deformation=D.zone_deformation(zone, today), so2=D.so2_status(today),
                  so2_series=D.so2_series(today - dt.timedelta(days=days), today),
                  notes=dict(deformation="Estaciones GNSS públicas procesadas por NGL (placa africana fija). La serie final "
                                         "llega con unas 4 semanas de retraso: se evalúa el último día disponible.",
                             so2="SO2 visible por satélite (OMPS) sobre el archipiélago, por encima de 1 DU. Detecta "
                                 "erupciones y desgasificación fuerte, no la difusa previa (CO2, He).")))


@lru_cache(maxsize=32)
def _canarias_zones_cached(t_bucket: int, n_cat: int) -> dict:
    from .. import deformation as D
    from ..calibration import context_line
    cat = _catalog()
    t_at = float(t_bucket)
    day = dt.datetime.fromtimestamp(t_at, dt.timezone.utc).date()
    try:
        cal = _calibration()
    except Exception:
        cal = None
    out = []
    for z in ZONES:
        zc = store.zone_catalog(cat, z.key)
        u = unrest(zc, t_at)
        last30 = zc.window(t_at - 30 * DAY, t_at)
        out.append(dict(key=z.key, name=z.name, note=z.note, centroid=z.centroid,
                        bbox=[z.lat_min, z.lat_max, z.lon_min, z.lon_max],
                        index=u.index, components=u.components, rate_ratio=u.rate_ratio, energy_ratio=u.energy_ratio,
                        shallowing_km=u.shallowing_km, n7=u.recent.n, n30=len(last30),
                        max_mag30=float(np.nanmax(last30.mag)) if len(last30) and not np.all(np.isnan(last30.mag)) else None,
                        depth_median30=float(np.nanmedian(last30.depth)) if len(last30) and not np.all(np.isnan(last30.depth)) else None,
                        daily30=_daily_counts(zc, t_at, 30),
                        b=None if u.recent.b is None else dict(b=u.recent.b.b, sigma=u.recent.b.sigma, mc=u.recent.b.mc, n=u.recent.b.n),
                        mc=u.mc, rate_surprise=u.rate_surprise, history=context_line(cal, z.key, u.index),
                        deformation=_deform_summary(D.zone_deformation(z.key, day))))
    out.sort(key=lambda d: -(d["index"] or -1))
    return _clean(dict(at=dt.datetime.fromtimestamp(t_at, dt.timezone.utc).isoformat(), zones=out, so2=D.so2_status(day),
                       note="Índice de actividad anómala 0-10 frente a la línea base propia de cada zona. NO es probabilidad de erupción; las alertas oficiales son del PEVOLCA."))


@app.get("/api/canarias/zones")
def canarias_zones(at: str | None = None):
    cat = _catalog()
    t_bucket = int(dt.datetime.fromisoformat(at).timestamp()) if at else int(time.time() // 60) * 60
    return JSONResponse(_canarias_zones_cached(t_bucket, len(cat)))


def _deform_summary(zd: dict) -> dict:
    st = [s for s in zd["stations"] if s["level"] in ("normal", "a vigilar", "anómala")]
    return dict(level=zd["level"], n_stations=len(st),
                evaluated_at=max((s["evaluated_at"] for s in st), default=None),
                worst=max(st, key=lambda s: max(s.get("z_h") or 0, abs(s.get("z_u") or 0)), default=None))


@app.get("/api/canarias/quakes")
def canarias_quakes(days: float = 30, start: str | None = None, end: str | None = None, zone: str | None = None,
                    min_mag: float | None = None, limit: int = 20000):
    e = dt.datetime.fromisoformat(end) if end else dt.datetime.now(dt.timezone.utc)
    s = dt.datetime.fromisoformat(start) if start else e - dt.timedelta(days=days)
    ev = store.events_between(s, e, zone=zone, min_mag=min_mag, limit=limit)
    if ev:
        x, y = lonlat_to_utm28(np.array([q["lon"] for q in ev]), np.array([q["lat"] for q in ev]))
        for q, xi, yi in zip(ev, x, y):
            q["x"], q["y"] = float(xi), float(yi)
    return J(dict(start=s.isoformat(), end=e.isoformat(), n=len(ev), quakes=ev, citation=store.status()["citation"]))


@app.post("/api/canarias/refresh")
def canarias_refresh(request: Request):
    need(request, "tecnico")
    return J(store.refresh_live())


# ------------------------------------------------------------------ solunar
@lru_cache(maxsize=64)
def _solunar_cached(zone: str, start: str, end_key: str, min_mag: float | None, n_cat: int) -> dict:
    cat = store.zone_catalog(_catalog(), zone)
    s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp()
    e = dt.datetime.fromisoformat(end_key).replace(tzinfo=dt.timezone.utc).timestamp()
    w = cat.window(s, e)
    if min_mag is not None:
        w = w.select(np.nan_to_num(w.mag, nan=-9) >= min_mag)
    lat, lon = BY_KEY[zone].centroid
    res = dict(zone=zone, n=len(w), start=start, end=end_key)
    if len(w) >= 20:
        year = 365.25 * DAY
        clock = TidalClock(lat, lon, w.t.min() - year, w.t.max() + year)
        fns = dict(semidiurnal=(clock.phase, SEMIDIURNAL_S), fortnightly=(lambda t: (2 * lunar_elongation(t)) % 360, SPRING_NEAP_S))
        keep = decluster(w.t, w.mag, hours=6)
        for name, (fn, period) in fns.items():
            arr = fn(w.t)
            h, _ = np.histogram(arr[~np.isnan(arr)], bins=12, range=(0, 360))
            res[name] = dict(raw=schuster(arr), declustered=schuster(arr[keep]), hist12=h.tolist(),
                             shift_test=alignment_shift_test(w.t[keep], fn, period, n_perm=200))
    return _clean(res)


@app.get("/api/solunar")
def solunar(zone: str = "la_palma", start: str = "2011-01-01", end: str | None = None, min_mag: float | None = None):
    if zone not in BY_KEY:
        raise HTTPException(404, "zona desconocida")
    cat = _catalog()
    end_key = end or dt.datetime.now(dt.timezone.utc).date().isoformat()
    res = dict(_solunar_cached(zone, start, end_key, min_mag, len(cat)))
    res["end"] = end
    lat, lon = BY_KEY[zone].centroid
    now = time.time()
    res["now"] = dict(tidal_phase=float(tidal_phase([now], lat, lon)[0]), lunar_elongation=float(lunar_elongation(now)))
    res["note"] = ("Schuster: p<0,05 = fases no uniformes (no prueba causalidad); los enjambres inflan la significación. "
                   "La prueba robusta es 'shift_test': exceso de sismos en fase 0 (máximo de marea / mareas vivas) frente a "
                   "200 desplazamientos temporales del propio catálogo desagrupado (1 sismo/6 h).")
    return JSONResponse(res)


# ------------------------------------------------------------------ La Palma 2021
_replay_lock = threading.Lock()
_replay = dict(obj=None)


def replay():
    with _replay_lock:
        if _replay["obj"] is None:
            from ..replay import LaPalma2021
            _replay["obj"] = LaPalma2021(catalog=_catalog())
        return _replay["obj"]


MILESTONES = [
    ("2021-09-11", "Empieza el enjambre sísmico bajo Cumbre Vieja"),
    ("2021-09-13", "Semáforo amarillo en El Paso, Los Llanos, Mazo y Fuencaliente"),
    ("2021-09-19", "14:10 UTC · Comienza la erupción en Cabeza de Vaca"),
    ("2021-09-21", "La colada alcanza Todoque"),
    ("2021-09-28", "22:02 UTC · La lava llega al mar (Los Guirres, Tazacorte)"),
    ("2021-10-04", "Colapso del cono principal"),
    ("2021-10-14", "La colada norte entra en La Laguna"),
    ("2021-11-15", "Tercera llegada al mar"),
    ("2021-12-13", "Cesa la actividad (85 días)"),
    ("2021-12-25", "Fin oficial de la erupción"),
]


@app.get("/api/lapalma2021/meta")
def lp_meta():
    r = replay()
    g = r.grid
    places = []
    for p in r.places["places"]:
        x, y = lonlat_to_utm28(p["lon"], p["lat"])
        places.append(dict(p, x=float(x), y=float(y)))
    from ..replay import replay_days
    return J(dict(
        onset=LAPALMA_2021_ONSET.isoformat(), days=[d.isoformat() for d in replay_days()],
        vent=dict(lonlat=r.vent_lonlat(), xy=r.vent_xy),
        lava_grid=dict(west=g.west, north=g.north, step=g.step, rows=g.shape[0], cols=g.shape[1]),
        places=places, places_attribution=r.places["attribution"],
        observations=[dict(at=o.observed_at.isoformat(), area_ha=o.area_ha_reported) for o in r.obs],
        milestones=[dict(date=d, text=t) for d, t in MILESTONES],
        sources=["Copernicus EMS EMSR546 (© 2021 EU)", "IGN · Catálogo de terremotos (doi:10.7419/162.03.2022)",
                 "Copernicus DEM GLO-30 (pre-erupción)", "© OpenStreetMap (ODbL) · topónimos"]))


@lru_cache(maxsize=256)
def _lp_day(date: str):
    cf = CACHE / "lp_days" / f"{date}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass
    r = replay()
    d = dt.date.fromisoformat(date)
    now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
    seis = r.seismic_state(now)
    lava = r.lava_state(now)
    out = dict(date=date, now=now.isoformat(), seismic=seis, lava={k: v for k, v in lava.items() if k != "_fc"},
               indicators=_lp_indicators(d))
    if lava.get("phase") == "eruptive":
        fc = lava["_fc"]
        ks = r.obs_until(now)
        obs = r.mask(ks[-1]).reshape(r.grid.shape) if ks else None
        horizon = r.hours(now) + 72
        out["overlay"] = dict(png=png_data_url(lava_overlay_rgba(fc.probability(horizon), obs), "RGBA"),
                              horizon_h=72, west=r.grid.west, north=r.grid.north, step=r.grid.step,
                              rows=r.grid.shape[0], cols=r.grid.shape[1],
                              legend="Probabilidad de cubrimiento en las próximas 72 h · mancha oscura con borde naranja = último mapa de Copernicus ya entregado")
    res = _clean(out)
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(res))
    except Exception:
        pass
    return res


def _lp_indicators(d: dt.date) -> dict:
    """GNSS displacement since 10 Sep 2021 (before the swarm) and satellite SO2, as known on day d."""
    from .. import deformation as D
    G = D.load_gnss()
    gnss = []
    for code in ("MAZO", "LPAL"):
        if code in G:
            disp = D.displacement_since(G[code], dt.date(2021, 9, 10), d)
            a = D.station_anomaly(G[code], d)
            gnss.append(dict(code=code, place=G[code]["place"], since="2021-09-10", disp_mm=disp,
                             level=a["level"] if a else "sin datos"))
    rows = D.so2_series(dt.date(2021, 9, 1), d)
    return dict(gnss=gnss, so2=D.so2_status(d), so2_series=[dict(date=r["date"], kt=r["so2_kt"]) for r in rows])


@app.get("/api/lapalma2021/day/{date}")
def lp_day(date: str):
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "fecha inválida")
    return JSONResponse(_lp_day(date))


@lru_cache(maxsize=2)
def _lp_quakes():
    ev = store.events_between(dt.datetime(2021, 8, 1, tzinfo=dt.timezone.utc), dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc),
                              zone="la_palma")
    if ev:
        x, y = lonlat_to_utm28(np.array([q["lon"] for q in ev]), np.array([q["lat"] for q in ev]))
        for q, xi, yi in zip(ev, x, y):
            q["x"], q["y"] = float(xi), float(yi)
    return _clean(dict(n=len(ev), quakes=ev))


@app.get("/api/lapalma2021/quakes")
def lp_quakes():
    return JSONResponse(_lp_quakes())


_impact = dict(obj=None)


def impact_replay():
    with _replay_lock:
        r = _replay["obj"]
    if r is None:
        r = replay()
    with _replay_lock:
        if _impact["obj"] is None:
            from ..replay import ImpactReplay
            _impact["obj"] = ImpactReplay(r)
        return _impact["obj"]


@lru_cache(maxsize=256)
def _lp_impact(date: str):
    cf = CACHE / "lp_impact" / f"{date}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text())
        except Exception:
            pass
    d = dt.date.fromisoformat(date)
    now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
    ir = impact_replay()
    if now < LAPALMA_2021_ONSET:
        sc = ir.scenario(now)
        res = _clean(dict(date=date, phase="pre-eruptive", scenario=sc))
    else:
        res = _clean(dict(date=date, **ir.eruptive(now)))
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(res))
    except Exception:
        pass
    return res


@app.get("/api/lapalma2021/impact/{date}")
def lp_impact(date: str):
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "fecha inválida")
    return JSONResponse(_lp_impact(date))


@app.get("/api/lapalma2021/validation")
def lp_validation():
    f = CACHE / "validation_lapalma2021.json"
    if f.exists():
        return JSONResponse(json.loads(f.read_text()))
    from ..replay import validation_payload
    res = _clean(validation_payload(impact_replay()))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res))
    return JSONResponse(res)


# ------------------------------------------------------------------ interoperability: CAP 1.2 and OGC API Features
def _lp_bands(date: str):
    """Probability bands of new lava within 72 h (area-constrained, as the impact panel) for a replay day."""
    from ..geoexport import probability_bands
    d = dt.date.fromisoformat(date)
    now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
    ir = impact_replay()
    q = ir.coverage_map(now) if now >= LAPALMA_2021_ONSET else None
    if q is None:
        return None, None
    return probability_bands(ir.r.grid, q), now


def _tf(key: str):
    from ..tenerife import grid as tf_grid, probability_raster, scenario
    with _tf_lock:
        sc = scenario(key, _catalog())
    if sc is None or sc.get("unavailable"):
        raise HTTPException(404, "escenario desconocido o sin datos")
    return sc, probability_raster(sc), tf_grid()


@app.get("/api/cap/lapalma2021/{date}.xml")
def cap_lapalma(date: str, request: Request):
    need(request, "tecnico")
    from .. import cap
    try:
        bands, now = _lp_bands(date)
    except ValueError:
        raise HTTPException(400, "fecha inválida")
    if not bands:
        raise HTTPException(404, "ese día aún no hay pronóstico de colada (no hay mapa de Copernicus entregado)")
    imp = _lp_impact(date)
    c = imp.get("constrained") or {}
    b, r = c.get("buildings", {}), c.get("road_km", {})
    iso = [i for i in imp.get("isolation", []) if i["p_isolated"] >= 0.1]
    desc = (f"Reconstrucción de La Palma 2021 con los datos disponibles el {date}. En las próximas 72 h se esperan "
            f"{b.get('central')} edificios nuevos alcanzados (rango {b.get('low')}–{b.get('high')}) y {r.get('central')} km de vías. "
            f"{len(iso)} núcleos podrían quedar aislados. Polígonos: probabilidad de que la colada cubra cada zona en 72 h.")
    xml = cap.build(kind="lapalma2021", ref=date, sent=now, headline=f"La Palma 2021 · impacto previsto a 72 h ({date}) · simulación",
                    description=desc, bands=bands, isolated=iso, expires=now + dt.timedelta(hours=72),
                    parameters={"horizonte_h": 72, "edificios_central": b.get("central"), "edificios_p10": b.get("low"),
                                "edificios_p90": b.get("high"), "vias_km_central": r.get("central"), "fuente": "VolScan"})
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="volscan_cap_lapalma2021_{date}.xml"'})


@app.get("/api/cap/tenerife/{key}.xml")
def cap_tenerife(key: str, request: Request):
    need(request, "tecnico")
    from .. import cap
    from ..geoexport import probability_bands
    sc, p, g = _tf(key)
    bands = probability_bands(g, p) if p is not None else []
    iso = [i for i in sc.get("isolation", []) if i["p_isolated"] >= 0.05]
    b = sc["buildings"]
    desc = (f"Escenario de planificación «{sc['name']}» ({sc.get('history') or ''}). Si se abriera una boca ahí, en 30 días la "
            f"colada alcanzaría {round(b['expected'])} edificios de media (P10–P90 {round(b['p10_p90'][0])}–{round(b['p10_p90'][1])}) "
            f"y {round(sc['road_km']['expected'], 1)} km de vías. No indica que una erupción sea probable.")
    xml = cap.build(kind="tenerife", ref=key, sent=dt.datetime.now(dt.timezone.utc),
                    headline=f"Tenerife · escenario {sc['name']} · planificación", description=desc, bands=bands, isolated=iso,
                    parameters={"horizonte_h": sc["horizon_h"], "edificios_media": round(b["expected"]),
                                "vias_km_media": round(sc["road_km"]["expected"], 1), "fuente": "VolScan"})
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="volscan_cap_tenerife_{key}.xml"'})


OGC_COLLECTIONS = {
    "zonas": "Zonas volcánicas de Canarias (cada isla con su mar hasta 25 km, y el canal de Enmedio)",
    "estaciones-gnss": "Estaciones GNSS públicas con su desviación respecto a la tendencia (NGL)",
    "sismos-30d": "Sismos de los últimos 30 días (catálogo IGN)",
    "lapalma2021-colada-72h": "La Palma 2021: probabilidad de colada nueva en 72 h (parámetro fecha=AAAA-MM-DD)",
    "lapalma2021-colada-observada": "La Palma 2021: último mapa de Copernicus entregado (parámetro fecha)",
    "lapalma2021-edificios-riesgo": "La Palma 2021: edificios con probabilidad de ser alcanzados en 72 h (parámetro fecha)",
    "tenerife-escenario": "Tenerife: probabilidad de colada en 30 días (parámetro escenario=" +
                          "dorsal_noroeste|pico_viejo|teide_norte|dorsal_noreste|sismicidad_actual)",
    "tenerife-servicios": "Tenerife: servicios e infraestructuras alcanzables por escenario (parámetro escenario)",
}


def _ogc_base(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/ogc"


@app.get("/ogc")
def ogc_landing(request: Request):
    b = _ogc_base(request)
    return J(dict(title="VolScan · OGC API Features", description="Capas de VolScan para QGIS, ArcGIS y visores OGC.",
                  links=[dict(href=b, rel="self", type="application/json"),
                         dict(href=f"{b}/conformance", rel="conformance", type="application/json"),
                         dict(href=f"{b}/collections", rel="data", type="application/json")]))


@app.get("/ogc/conformance")
def ogc_conformance():
    return J(dict(conformsTo=["http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
                              "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson"]))


def _coll(request: Request, cid: str) -> dict:
    b = _ogc_base(request)
    return dict(id=cid, title=OGC_COLLECTIONS[cid], itemType="feature", crs=["http://www.opengis.net/def/crs/OGC/1.3/CRS84"],
                links=[dict(href=f"{b}/collections/{cid}/items", rel="items", type="application/geo+json")])


@app.get("/ogc/collections")
def ogc_collections(request: Request):
    return J(dict(collections=[_coll(request, c) for c in OGC_COLLECTIONS],
                  links=[dict(href=f"{_ogc_base(request)}/collections", rel="self", type="application/json")]))


@app.get("/ogc/collections/{cid}")
def ogc_collection(cid: str, request: Request):
    if cid not in OGC_COLLECTIONS:
        raise HTTPException(404, "colección desconocida")
    return J(_coll(request, cid))


@lru_cache(maxsize=1)
def _zone_features():
    from ..geoexport import mask_polygons
    from ..zones import BY_KEY, _raster
    label, lat1, lon0, res, keys = _raster()
    feats = []
    for k, key in enumerate(keys):
        if key == "atlantico":
            continue
        polys = mask_polygons((lon0, lat1, res), label == k, tol_cells=1.0)
        feats.append(dict(type="Feature", id=key, properties=dict(key=key, name=BY_KEY[key].name, note=BY_KEY[key].note),
                          geometry=dict(type="MultiPolygon", coordinates=[q["coordinates"] for q in polys])))
    return feats


@app.get("/ogc/collections/{cid}/items")
def ogc_items(cid: str, request: Request, fecha: str = "2021-09-25", escenario: str = "dorsal_noroeste", limit: int = 10000):
    from ..geoexport import feature_collection
    if cid not in OGC_COLLECTIONS:
        raise HTTPException(404, "colección desconocida")
    pt = lambda lon, lat, props, fid=None: dict(type="Feature", id=fid, properties=props,
                                                geometry=dict(type="Point", coordinates=[round(lon, 6), round(lat, 6)]))
    feats: list = []
    if cid == "zonas":
        feats = _zone_features()
    elif cid == "estaciones-gnss":
        from .. import deformation as D
        today = dt.datetime.now(dt.timezone.utc).date()
        for z in ZONES:
            for s_ in D.zone_deformation(z.key, today)["stations"]:
                feats.append(pt(s_["lon"], s_["lat"], {k: v for k, v in s_.items() if k not in ("lon", "lat")} | dict(zone=z.key), s_["code"]))
    elif cid == "sismos-30d":
        e = dt.datetime.now(dt.timezone.utc)
        for q in store.events_between(e - dt.timedelta(days=30), e, limit=limit):
            feats.append(pt(q["lon"], q["lat"], dict(t=q["t"], mag=q["mag"], depth_km=q["depth"], zone=q["zone"], place=q["place"]), q["id"]))
    elif cid.startswith("lapalma2021-"):
        try:
            d = dt.date.fromisoformat(fecha)
        except ValueError:
            raise HTTPException(400, "fecha inválida (AAAA-MM-DD)")
        now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
        if cid == "lapalma2021-colada-72h":
            feats = _lp_bands(fecha)[0] or []
        elif cid == "lapalma2021-colada-observada":
            o = replay().observed_geojson(now)
            feats = [dict(o, id="observada")] if o else []
        else:
            from ..geo import utm28_to_lonlat
            for k, (x, y, v) in enumerate(_lp_impact(fecha).get("buildings_at_risk_xy") or []):
                lon, lat = utm28_to_lonlat(x, y)
                feats.append(pt(float(lon), float(lat), dict(p_72h=v), k))
    elif cid.startswith("tenerife-"):
        sc, p, g = _tf(escenario)
        if cid == "tenerife-escenario":
            from ..geoexport import probability_bands
            feats = probability_bands(g, p) if p is not None else []
        else:
            feats = [pt(f["lon"], f["lat"], dict(kind=f["kind"], name=f["name"], p_30d=f["p"], eta_p50_h=f["eta_h"][1]), k)
                     for k, f in enumerate(sc.get("facilities", []))]
    feats = feats[:limit]
    fc = feature_collection(_clean(feats), numberReturned=len(feats), timeStamp=dt.datetime.now(dt.timezone.utc).isoformat())
    return JSONResponse(fc, media_type="application/geo+json")


# ------------------------------------------------------------------ exports: PDF and CSV
def _file(content: bytes, media: str, name: str) -> Response:
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/export/report/{zone}/{month}.{fmt}")
def export_report(zone: str, month: str, fmt: str, request: Request):
    need(request, "tecnico")
    from .. import pdfexport as X
    if zone not in BY_KEY or zone == "atlantico" or fmt not in ("pdf", "csv"):
        raise HTTPException(404, "no existe")
    try:
        from ..reports import month_bounds
        month_bounds(month)
    except Exception:
        raise HTTPException(400, "mes inválido (AAAA-MM)")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    r = _report(zone, month, today, len(store.load_events()))
    if fmt == "pdf":
        return _file(X.report_pdf(r), "application/pdf", f"volscan_informe_{zone}_{month}.pdf")
    return _file(X.report_csv(r), "text/csv; charset=utf-8", f"volscan_informe_{zone}_{month}.csv")


@app.get("/api/export/impact/lapalma2021/{date}.{fmt}")
def export_lp_impact(date: str, fmt: str, request: Request):
    need(request, "tecnico")
    if fmt not in ("pdf", "csv"):
        raise HTTPException(404, "no existe")
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "fecha inválida")
    from .. import pdfexport as X
    imp = _lp_impact(date)
    if imp.get("phase") != "eruptive":
        raise HTTPException(404, "antes de la erupción no hay parte de impacto (ver escenario anticipado)")
    fac, iso = imp.get("facilities", []), imp.get("isolation", [])
    if fmt == "csv":
        return _file(X.impact_csv(fac, iso), "text/csv; charset=utf-8", f"volscan_impacto_lapalma2021_{date}.csv")
    c = imp.get("constrained")
    w = imp.get("watch") or {}
    if c:
        b, r_ = c.get("buildings") or {}, c.get("road_km") or {}
        b_val, b_rng = str(b.get("central", "—")), f"{b.get('low', '—')}–{b.get('high', '—')}"
        r_val, r_rng = str(r_.get("central", "—")), f"{r_.get('low', '—')}–{r_.get('high', '—')}"
        map_val, map_note = f"hace {c.get('map_age_h', '—')} h", f"se supone entregado {imp.get('map_delay_h')} h tras la imagen"
    else:
        b, r_ = imp.get("buildings") or {}, imp.get("road_km") or {}
        bp, rp = b.get("p10_p90") or ["—", "—"], r_.get("p10_p90") or ["—", "—"]
        b_val = str(round(b["expected"])) if "expected" in b else "—"
        b_rng = f"P10–P90 {round(bp[0])}–{round(bp[1])}" if isinstance(bp[0], (int, float)) else "—"
        r_val = str(round(r_["expected"], 1)) if "expected" in r_ else "—"
        r_rng = f"P10–P90 {rp[0]}–{rp[1]}"
        map_val, map_note = "aún no entregado", "pronóstico solo con el conjunto inicial desde la boca"
    kpis = [("Edificios nuevos en 72 h", b_val, b_rng),
            ("Vías nuevas en 72 h (km)", r_val, r_rng),
            ("Edificios ya perdidos", str(imp["already_lost"]["buildings"]), f"{imp['already_lost']['road_km']} km de vías"),
            ("Lista de vigilancia", f"{w.get('high', '—')} alcanzables", f"{w.get('pocket', '—')} cercados por la colada"),
            ("Último mapa de Copernicus", map_val, map_note)]
    pdf = X.impact_pdf(f"La Palma 2021 · impacto previsto a 72 h · {date}", "Reconstrucción con los datos disponibles ese día (simulación, no alerta).",
                       kpis, fac, iso, [], imp.get("method", ""), "Copernicus EMS EMSR546, IGN, Copernicus DEM, OpenStreetMap (ODbL)")
    return _file(pdf, "application/pdf", f"volscan_impacto_lapalma2021_{date}.pdf")


@app.get("/api/export/impact/tenerife/{key}.{fmt}")
def export_tf_impact(key: str, fmt: str, request: Request):
    need(request, "tecnico")
    if fmt not in ("pdf", "csv"):
        raise HTTPException(404, "no existe")
    from .. import pdfexport as X
    sc, _, _ = _tf(key)
    fac, iso = sc.get("facilities", []), sc.get("isolation", [])
    if fmt == "csv":
        return _file(X.impact_csv(fac, iso), "text/csv; charset=utf-8", f"volscan_escenario_tenerife_{key}.csv")
    b, r_ = sc["buildings"], sc["road_km"]
    kpis = [("Edificios alcanzables (30 días)", str(round(b["expected"])), f"P10–P90 {round(b['p10_p90'][0])}–{round(b['p10_p90'][1])}"),
            ("Vías (km)", f"{r_['expected']:.1f}".replace(".", ","), f"P10–P90 {r_['p10_p90'][0]:.1f}–{r_['p10_p90'][1]:.1f}"),
            ("Edificios con P >= 5 %", str(sc.get("n_buildings_exposed", "—")), sc.get("exposure_note", "")),
            ("Recorridos que llegan al mar", f"{round(100 * sc.get('reach_sea', 0))} %", f"{sc.get('n_paths')} recorridos de colada")]
    pdf = X.impact_pdf(f"Tenerife · escenario {sc['name']}", f"{sc.get('history') or ''} · escenario de planificación, no pronóstico.",
                       kpis, fac, iso, sc.get("places", []),
                       "Conjunto de coladas (mismo motor validado en La Palma 2021) desde los centros eruptivos históricos, con "
                       "700–800 m de incertidumbre; impacto sobre OpenStreetMap. Parámetros basálticos.",
                       "Copernicus DEM GLO-30, OpenStreetMap (ODbL), IGN")
    return _file(pdf, "application/pdf", f"volscan_escenario_tenerife_{key}.pdf")


def _fallback_brief(day: dict) -> str:
    s, l = day.get("seismic") or {}, day.get("lava") or {}
    lines = [f"Resumen automático sin modelo de lenguaje · {day['date']}"]
    if s:
        lines.append(f"Sismicidad La Palma (24 h): {s['last24h']['n']} eventos, magnitud máxima "
                     f"{s['last24h']['max_mag'] if s['last24h']['max_mag'] is not None else '—'}, profundidad mediana "
                     f"{round(s['last24h']['depth_median_km'], 1) if s['last24h']['depth_median_km'] is not None else '—'} km. "
                     f"Índice de actividad anómala: {s['unrest_index'] if s['unrest_index'] is not None else 'sin línea base'} / 10.")
    if l.get("phase") == "eruptive":
        sea = l["sea"]
        lines.append(f"Probabilidad de que la colada alcance el mar: {round(100 * sea['p_ever'])} %"
                     + (f"; llegada estimada P10–P90: {sea['eta_h'][0]}–{sea['eta_h'][2]} h." if sea["eta_h"][1] is not None else "."))
        top = [p for p in l["places"] if p["p_ever"] >= 0.05][:4]
        if top:
            lines.append("Núcleos con probabilidad ≥5 %: " + "; ".join(
                f"{p['name']} {round(100 * p['p_ever'])} %" + (f" (P50 {p['eta_h'][1]} h)" if p["eta_h"][1] is not None else "")
                for p in top) + ".")
        o = l.get("observation")
        if o and o.get("front_stalled") and o.get("area_growing"):
            lines.append("El frente está detenido pero el área crece: posible acumulación y nuevos desbordamientos.")
    lines.append("VolScan no emite niveles de alerta: consulte al PEVOLCA.")
    return "\n".join(lines)


class BriefReq(BaseModel):
    regenerate: bool = False


@app.post("/api/lapalma2021/briefing/{date}")
def lp_briefing(date: str, request: Request, req: BriefReq = BriefReq()):
    if req.regenerate:
        need(request, "tecnico")
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "fecha inválida")
    day = _lp_day(date)
    cfg = llm.LLMConfig.from_env()
    f = CACHE / "briefings" / f"lapalma2021_{date}_{cfg.provider}_{cfg.model.replace(':', '_').replace('/', '_')}.json"
    if f.exists() and not req.regenerate:
        return JSONResponse(json.loads(f.read_text()))
    idx = rag.get_index(store.load_events(), replay().obs)
    hits = idx.search(f"La Palma 2021 erupción Tajogaite {date} sismos colada", k=5)
    live = {k: day[k] for k in ("date", "seismic", "lava")}
    question = (f"Redacta el parte de situación de VolScan para el {date} (fin del día, UTC), como si fuera ese día: "
                "solo con la información disponible hasta entonces. Estructura: 1) Sismicidad, 2) Colada y pronóstico "
                "(probabilidades y P10–P90), 3) Núcleos en riesgo, 4) Incertidumbres. Máximo 180 palabras. "
                "No menciones hechos posteriores a esa fecha.")
    try:
        text = llm.chat(rag.build_prompt(question, hits, live), cfg)
        res = dict(date=date, text=text, model=cfg.public(), ai=True, citations=rag.cite(hits))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(res, ensure_ascii=False))
    except llm.LLMUnavailable as e:
        res = dict(date=date, text=_fallback_brief(day), model=cfg.public(), ai=False, error=str(e), citations=[])
    return JSONResponse(res)


# ------------------------------------------------------------------ monthly reports
@app.get("/api/reports/months")
def report_months():
    from ..reports import available_months
    return J(dict(months=available_months(_catalog()), zones=[dict(key=z.key, name=z.name) for z in ZONES]))


@lru_cache(maxsize=512)
def _report(zone: str, month: str, today: str, n_events: int = 0):
    from ..reports import monthly_report
    cat = store.zone_catalog(_catalog(), zone)
    ev = [e for e, k in zip(store.load_events(), store.event_zone_keys()) if k == zone]
    return _clean(monthly_report(cat, ev, zone, month, indicators=True))


@app.get("/api/reports/monthly")
def report_monthly(zone: str = "tenerife", month: str | None = None):
    if zone not in BY_KEY or zone == "atlantico":
        raise HTTPException(404, "zona desconocida")
    month = month or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
    try:
        from ..reports import month_bounds
        month_bounds(month)
    except Exception:
        raise HTTPException(400, "mes inválido (AAAA-MM)")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return JSONResponse(_report(zone, month, today, len(store.load_events())))


@app.get("/api/reports/catastrophe/lapalma2021")
def report_catastrophe_lapalma():
    f = CACHE / "catastrophe_lapalma2021.json"
    if f.exists():
        return JSONResponse(json.loads(f.read_text()))
    from ..reports import catastrophe_report_lapalma2021
    res = _clean(catastrophe_report_lapalma2021(impact_replay()))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res, ensure_ascii=False))
    return JSONResponse(res)


class RewriteReq(BaseModel):
    zone: str
    month: str


@app.post("/api/reports/rewrite")
def report_rewrite(req: RewriteReq, request: Request):
    need(request, "tecnico")
    """The language model rewrites the summary in an institutional register WITHOUT adding facts (the figures go in as data)."""
    if req.zone not in BY_KEY or req.zone == "atlantico":
        raise HTTPException(404, "zona desconocida")
    try:
        from ..reports import month_bounds
        month_bounds(req.month)
    except Exception:
        raise HTTPException(400, "mes inválido (AAAA-MM)")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    rep = _report(req.zone, req.month, today, len(store.load_events()))
    cfg = llm.LLMConfig.from_env()
    facts = {k: rep.get(k) for k in ("title", "partial", "stats", "prev", "baseline", "rate_ratio", "b", "unrest_end", "top_events", "felt",
                                     "tides", "deformation", "so2")}
    msgs = [dict(role="system", content=(
        "Redactas el resumen del informe mensual de vigilancia sísmica de VolScan para un Cabildo. Español institucional, "
        "claro, 120-170 palabras, en un párrafo. Usa EXCLUSIVAMENTE las cifras del JSON; no añadas hechos, causas ni "
        "previsiones. Termina indicando que la valoración oficial corresponde al PEVOLCA.")),
        dict(role="user", content=json.dumps(facts, ensure_ascii=False, default=str)[:6000])]
    try:
        return JSONResponse(dict(text=llm.chat(msgs, cfg, max_tokens=500), ai=True, model=cfg.public()))
    except llm.LLMUnavailable as e:
        return JSONResponse(dict(text=None, ai=False, error=str(e), model=cfg.public()))


# ------------------------------------------------------------------ hexagonal AI: Meta SAM 3.1 + Muse Spark / Llama Agent
@app.get("/api/ai/architecture")
@app.get("/api/architecture")
def ai_architecture():
    from ..application import get_container
    return J(get_container().manifest())


class SwitchAdapterReq(BaseModel):
    preset: str = "meta_muse"       # "meta_muse" | "meta_llama4" | "meta_llama3_70b" | "ollama_local" | "auto"
    model: str | None = None
    base: str | None = None
    api_key: str | None = None


@app.post("/api/ai/adapter")
def switch_ai_adapter(req: SwitchAdapterReq, request: Request):
    need(request, "tecnico")
    from ..application import META_MODEL_PRESETS, get_container
    if req.preset not in META_MODEL_PRESETS and req.preset not in ("auto", "meta", "llama", "ollama", "local"):
        raise HTTPException(400, f"preset desconocido: {req.preset}")
    c = get_container()
    st = c.switch_llm_adapter(req.preset, model=req.model, base=req.base, api_key=req.api_key)
    _llm_status["value"] = st
    _llm_status["at"] = time.time()
    return J(dict(ok=True, llm=st, architecture=c.manifest()))


@app.get("/api/lapalma2021/sam3/{date}")
def lp_sam3_assimilation(date: str):
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "fecha inválida")
    from ..ai.vision_service import sam3_scene_for_date
    from ..application import get_container
    return J(sam3_scene_for_date(date, lp=replay(), port=get_container().segmentation))


@app.get("/api/lapalma2021/sam3-validation")
def lp_sam3_validation():
    from ..ai.vision_service import sam3_validation_benchmark
    return J(sam3_validation_benchmark(impact_replay()))


class ChatReq(BaseModel):
    question: str
    context: str | None = None      # "canarias" | "tenerife" | "lapalma2021:YYYY-MM-DD"


@app.post("/api/chat")
@app.post("/api/ai/agent")
def chat(req: ChatReq, request: Request):
    need(request, "tecnico")
    if not req.question.strip():
        raise HTTPException(400, "pregunta vacía")
    if req.context and req.context.startswith("lapalma2021:"):
        date_str = req.context.split(":", 1)[1]
        try:
            dt.date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(400, "fecha inválida")
    from ..application import get_container
    agent = get_container().agent()
    res = agent.run(
        req.question,
        context=req.context,
        events=store.load_events(),
        lava_obs=replay().obs if _replay["obj"] else None,
    )
    return J(res)


# ------------------------------------------------------------------ web app
if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = WEB / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB / "index.html")
