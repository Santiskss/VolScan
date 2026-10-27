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
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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


@app.get("/api/status")
def status():
    if time.time() - _llm_status["at"] > 60:
        _llm_status["value"] = llm.ping()
        _llm_status["at"] = time.time()
    store.load_events()
    return J(dict(version=__version__, llm=_llm_status["value"], catalog=store.status(),
                  now=dt.datetime.now(dt.timezone.utc).isoformat()))


# ------------------------------------------------------------------ terrain
@lru_cache(maxsize=4)
def _terrain(name: str, texture_k: int):
    files = {"lapalma": DATA / "canarias" / "terrain_lapalma_100m.npz",
             "tenerife": DATA / "canarias" / "terrain_tenerife_100m.npz",
             "archipelago": DATA / "canarias" / "terrain_archipelago_500m.npz"}
    if name not in files:
        raise HTTPException(404, "terreno desconocido")
    g = load_grid_npz(files[name])
    zt = upsample(g.elev, texture_k) if texture_k > 1 else g.elev
    tex = relief_rgb(zt, g.step / texture_k, zmax=2200.0 if name == 'archipelago' else None,
                     sea=(203, 211, 214) if name == 'archipelago' else (214, 219, 221))
    return dict(name=name, crs="EPSG:4083", west=g.west, north=g.north, step=g.step, rows=g.shape[0], cols=g.shape[1],
                heights_i16_b64=heights_b64(g.elev), nodata=-32768, texture=png_data_url(tex, "RGB"),
                max_elev=float(np.nanmax(g.elev)),
                attribution="Copernicus DEM GLO-30 © DLR/Airbus, provided under COPERNICUS by the EU and ESA")


@app.get("/api/terrain/{name}")
def terrain(name: str):
    return J(_terrain(name, 4 if name == "lapalma" else 3 if name == "tenerife" else 2))


# ------------------------------------------------------------------ Tenerife scenarios
@app.get("/api/tenerife/scenarios")
def tf_scenarios():
    from ..tenerife import catalogue
    return J(dict(scenarios=catalogue(),
                  note="Escenarios de planificación con el mismo motor validado en La Palma 2021. No indican que una erupción sea "
                       "probable ni dónde ocurriría. La valoración oficial corresponde al PEVOLCA."))


_tf_lock = threading.Lock()


@app.get("/api/tenerife/scenario/{key}")
def tf_scenario(key: str):
    from ..tenerife import scenario
    with _tf_lock:
        out = scenario(key, _catalog())
    if out is None:
        raise HTTPException(404, "escenario desconocido")
    return J(out)


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


@app.get("/api/canarias/zones")
def canarias_zones(at: str | None = None):
    from .. import deformation as D
    from ..calibration import context_line
    cat = _catalog()
    t_at = dt.datetime.fromisoformat(at).timestamp() if at else time.time()
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
                        box=[z.lat_min, z.lat_max, z.lon_min, z.lon_max],
                        index=u.index, components=u.components, rate_ratio=u.rate_ratio, energy_ratio=u.energy_ratio,
                        shallowing_km=u.shallowing_km, n7=u.recent.n, n30=len(last30),
                        max_mag30=float(np.nanmax(last30.mag)) if len(last30) and not np.all(np.isnan(last30.mag)) else None,
                        depth_median30=float(np.nanmedian(last30.depth)) if len(last30) and not np.all(np.isnan(last30.depth)) else None,
                        daily30=_daily_counts(zc, t_at, 30),
                        b=None if u.recent.b is None else dict(b=u.recent.b.b, sigma=u.recent.b.sigma, mc=u.recent.b.mc, n=u.recent.b.n),
                        mc=u.mc, rate_surprise=u.rate_surprise, history=context_line(cal, z.key, u.index),
                        deformation=_deform_summary(D.zone_deformation(z.key, day))))
    out.sort(key=lambda d: -(d["index"] or -1))
    return J(dict(at=dt.datetime.fromtimestamp(t_at, dt.timezone.utc).isoformat(), zones=out, so2=D.so2_status(day),
                  note="Índice de actividad anómala 0-10 frente a la línea base propia de cada zona. NO es probabilidad de erupción; las alertas oficiales son del PEVOLCA."))


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
def canarias_refresh():
    return J(store.refresh_live())


# ------------------------------------------------------------------ solunar
@app.get("/api/solunar")
def solunar(zone: str = "la_palma", start: str = "2011-01-01", end: str | None = None, min_mag: float | None = None):
    if zone not in BY_KEY:
        raise HTTPException(404, "zona desconocida")
    cat = store.zone_catalog(_catalog(), zone)
    s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc).timestamp()
    e = dt.datetime.fromisoformat(end).replace(tzinfo=dt.timezone.utc).timestamp() if end else time.time()
    w = cat.window(s, e)
    if min_mag is not None:
        w = w.select(np.nan_to_num(w.mag, nan=-9) >= min_mag)
    lat, lon = BY_KEY[zone].centroid
    res = dict(zone=zone, n=len(w), start=start, end=end)
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
    now = time.time()
    res["now"] = dict(tidal_phase=float(tidal_phase([now], lat, lon)[0]), lunar_elongation=float(lunar_elongation(now)))
    res["note"] = ("Schuster: p<0,05 = fases no uniformes (no prueba causalidad); los enjambres inflan la significación. "
                   "La prueba robusta es 'shift_test': exceso de sismos en fase 0 (máximo de marea / mareas vivas) frente a "
                   "200 desplazamientos temporales del propio catálogo desagrupado (1 sismo/6 h).")
    return J(res)


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
        out["observed"] = r.observed_geojson(now)
    return _clean(out)


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
    d = dt.date.fromisoformat(date)
    now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
    ir = impact_replay()
    if now < LAPALMA_2021_ONSET:
        sc = ir.scenario(now)
        return _clean(dict(date=date, phase="pre-eruptive", scenario=sc))
    return _clean(dict(date=date, **ir.eruptive(now)))


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
def lp_briefing(date: str, req: BriefReq = BriefReq()):
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
def _report(zone: str, month: str, today: str):
    from ..reports import monthly_report
    from ..zones import zone_of
    cat = store.zone_catalog(_catalog(), zone)
    ev = [e for e in store.load_events() if zone_of(e.lat, e.lon).key == zone]
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
    return JSONResponse(_report(zone, month, dt.date.today().isoformat()))


class RewriteReq(BaseModel):
    zone: str
    month: str


@app.post("/api/reports/rewrite")
def report_rewrite(req: RewriteReq):
    """The language model rewrites the summary in an institutional register WITHOUT adding facts (the figures go in as data)."""
    rep = _report(req.zone, req.month, dt.date.today().isoformat())
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


# ------------------------------------------------------------------ chat (RAG)
class ChatReq(BaseModel):
    question: str
    context: str | None = None      # "canarias" | "lapalma2021:YYYY-MM-DD"


@app.post("/api/chat")
def chat(req: ChatReq):
    if not req.question.strip():
        raise HTTPException(400, "pregunta vacía")
    idx = rag.get_index(store.load_events(), replay().obs if _replay["obj"] else None)
    hits = idx.search(req.question, k=6)
    live = None
    if req.context and req.context.startswith("lapalma2021:"):
        day = _lp_day(req.context.split(":", 1)[1])
        live = {k: day[k] for k in ("date", "seismic", "lava")}
    elif req.context == "canarias":
        z = json.loads(canarias_zones().body)
        live = dict(at=z["at"], zonas=[{k: q[k] for k in ("name", "index", "n7", "n30", "max_mag30", "depth_median30")}
                                       for q in z["zones"]])
    cfg = llm.LLMConfig.from_env()
    try:
        answer = llm.chat(rag.build_prompt(req.question, hits, live), cfg)
        return JSONResponse(dict(answer=answer, ai=True, model=cfg.public(), citations=rag.cite(hits)))
    except llm.LLMUnavailable as e:
        return JSONResponse(dict(answer=None, ai=False, error=str(e), model=cfg.public(), citations=rag.cite(hits)))


# ------------------------------------------------------------------ web app
if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = WEB / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB / "index.html")
