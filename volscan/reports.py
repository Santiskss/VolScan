"""Monthly report per volcanic zone: what happened, compared with what is normal for that zone.

Designed for a Cabildo or the PEVOLCA's scientific committee to file month
after month: the same structure, the same figures, and their source. The
narrative text is generated from the figures (deterministic); a language
model can rewrite it on request, but the figures always come from here.
"""
from __future__ import annotations

import calendar
import datetime as dt

import numpy as np

from .seismic import DAY, Catalog, b_value, energy_joules, unrest
from .tides import SEMIDIURNAL_S, SPRING_NEAP_S, TidalClock, alignment_shift_test, decluster, lunar_elongation
from .zones import BY_KEY

MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def month_bounds(month: str):
    y, m = map(int, month.split("-"))
    a = dt.datetime(y, m, 1, tzinfo=dt.timezone.utc)
    b = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=dt.timezone.utc)
    return a, b


def _stats(c: Catalog) -> dict:
    m = c.mag[~np.isnan(c.mag)]
    d = c.depth[~np.isnan(c.depth)]
    return dict(n=len(c), max_mag=float(m.max()) if m.size else None,
                n_m2=int((m >= 2).sum()), n_m3=int((m >= 3).sum()),
                depth_median=float(np.median(d)) if d.size else None,
                depth_p10=float(np.percentile(d, 10)) if d.size else None,
                shallow_lt5=int((d < 5).sum()), energy_j=float(energy_joules(m).sum()) if m.size else 0.0)


def monthly_report(cat: Catalog, events, zone_key: str, month: str, now: dt.datetime | None = None,
                   indicators: bool = False) -> dict:
    """`cat` = catalogue already filtered to the zone; `events` = list of IgnEvent of the zone (for details).

    With `indicators`, it adds deformation (GNSS, at the last day with data
    within the month) and satellite SO2 (days above the detection threshold).
    """
    z = BY_KEY[zone_key]
    a, b = month_bounds(month)
    now = now or dt.datetime.now(dt.timezone.utc)
    end = min(b, now)
    partial = b > now
    cur = cat.window(a.timestamp(), end.timestamp())
    st = _stats(cur)
    days_in = (end - a).total_seconds() / DAY
    # previous month and 12-month baseline (monthly mean)
    pa, pb = month_bounds(f"{(a - dt.timedelta(days=1)):%Y-%m}")
    prev = _stats(cat.window(pa.timestamp(), pb.timestamp()))
    base = cat.window(a.timestamp() - 365 * DAY, a.timestamp())
    base_rate_day = len(base) / 365.0
    rate_day = st["n"] / days_in if days_in > 0 else float("nan")
    # daily series
    edges = np.arange(a.timestamp(), b.timestamp() + 1, DAY)
    daily, _ = np.histogram(cur.t, bins=edges)
    daily_depth = []
    for k in range(len(edges) - 1):
        w = cur.window(edges[k], edges[k + 1])
        dd = w.depth[~np.isnan(w.depth)]
        daily_depth.append(float(np.median(dd)) if dd.size else None)
    bv = b_value(cur.mag)
    u_end = unrest(cat, end.timestamp())
    # notable events
    evm = [e for e in events if a <= e.time_utc < end]
    top = sorted(evm, key=lambda e: -(e.mag if e.mag is not None else -9))[:10]
    felt = [e for e in evm if e.int_max]
    # tides for the month (declustered; few events → not computed)
    tides = None
    if st["n"] >= 30:
        lat, lon = z.centroid
        year = 365.25 * DAY
        clock = TidalClock(lat, lon, cur.t.min() - year, cur.t.max() + year)
        keep = decluster(cur.t, cur.mag, hours=6)
        tides = dict(
            semidiurnal=alignment_shift_test(cur.t[keep], clock.phase, SEMIDIURNAL_S, n_perm=100),
            fortnightly=alignment_shift_test(cur.t[keep], lambda t: (2 * lunar_elongation(t)) % 360, SPRING_NEAP_S, n_perm=100))
    rep = dict(
        zone=dict(key=z.key, name=z.name, note=z.note), month=month, title=f"{z.name} · {MESES[a.month - 1]} de {a.year}",
        partial=partial, generated_at=now.isoformat(), period=dict(start=a.isoformat(), end=end.isoformat()),
        stats=st, prev=prev, baseline=dict(rate_day=round(base_rate_day, 2), n_365=len(base)),
        rate_day=round(rate_day, 2), rate_ratio=round(rate_day / base_rate_day, 2) if base_rate_day > 0 else None,
        daily=daily.tolist(), daily_depth=daily_depth,
        b=None if bv is None else dict(b=round(bv.b, 2), sigma=round(bv.sigma, 2), mc=bv.mc, n=bv.n),
        unrest_end=dict(index=None if u_end.index is None else round(u_end.index, 1), components=u_end.components),
        top_events=[dict(t=e.time_utc.isoformat(), mag=e.mag, mag_type=e.mag_type, depth=e.depth_km, place=e.location,
                         int_max=e.int_max or None, id=e.evid) for e in top],
        felt=len(felt), tides=tides,
        sources=["Instituto Geográfico Nacional (IGN). Catálogo de terremotos. doi:10.7419/162.03.2022"],
        deformation=None, so2=None,
    )
    if indicators:
        from . import deformation as D
        last_day = (end - dt.timedelta(seconds=1)).date()
        zd = D.zone_deformation(zone_key, last_day)
        st_ok = [x for x in zd["stations"] if x["level"] in ("normal", "a vigilar", "anómala")]
        rep["deformation"] = dict(level=zd["level"], stations=st_ok) if st_ok else None
        rows = D.so2_series(a.date(), last_day)
        if rows:
            det = [r for r in rows if r["so2_kt"] >= D.SO2_DETECT_KT]
            rep["so2"] = dict(days=len(rows), days_detected=len(det), max_kt=max(r["so2_kt"] for r in rows),
                              threshold_kt=D.SO2_DETECT_KT)
        rep["sources"] += [D.ngl_gnss.CITATION, D.gibs_so2.CITATION]
    rep["summary"] = narrative(rep)
    return rep


def _n(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def _pl(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def narrative(r: dict) -> str:
    """Deterministic summary from the figures. Never says anything that isn't in the figures."""
    st, prev = r["stats"], r["prev"]
    parts = []
    period = "en lo que va de mes" if r["partial"] else "durante el mes"
    parts.append(f"{r['zone']['name']} registró {_pl(st['n'], 'terremoto localizado', 'terremotos localizados')} por el IGN {period}"
                 + (f", con magnitud máxima {_n(st['max_mag'])}" if st["max_mag"] is not None else "")
                 + (f"; {_pl(r['felt'], 'fue sentido', 'fueron sentidos')} por la población" if r["felt"] else "") + ".")
    if r["rate_ratio"] is not None:
        if r["rate_ratio"] >= 2:
            parts.append(f"Es {_n(r['rate_ratio'])} veces la tasa media de los doce meses anteriores.")
        elif r["rate_ratio"] <= 0.5:
            parts.append(f"Es una actividad inferior a la habitual ({_n(r['rate_ratio'])} veces la media anual).")
        else:
            parts.append("La actividad está dentro de lo habitual para la zona en el último año.")
    if st["depth_median"] is not None:
        parts.append(f"La mediana de profundidad fue de {_n(st['depth_median'])} km"
                     + (f" (el mes anterior, {_n(prev['depth_median'])} km)" if prev["depth_median"] is not None else "")
                     + (f"; {_pl(st['shallow_lt5'], 'evento', 'eventos')} a menos de 5 km." if st["shallow_lt5"] else "."))
    if st["n_m3"]:
        parts.append(f"Hubo {_pl(st['n_m3'], 'terremoto', 'terremotos')} de magnitud 3 o superior.")
    dfm = r.get("deformation")
    if dfm:
        worst = max(dfm["stations"], key=lambda x: max(x.get("z_h") or 0, abs(x.get("z_u") or 0)))
        lvl = {"normal": "dentro de lo normal", "a vigilar": "con desviaciones a vigilar", "anómala": "anómala"}[dfm["level"]]
        parts.append(f"Deformación (GNSS, {_pl(len(dfm['stations']), 'estación', 'estaciones')}): {lvl}; la mayor desviación, "
                     f"en {worst['code']}, fue de {_n(worst['anom_u_mm'])} mm en vertical respecto a su tendencia "
                     f"(datos hasta el {worst['evaluated_at']}).")
    so2 = r.get("so2")
    if so2:
        parts.append(f"SO2 por satélite: {'sin SO2 visible' if not so2['days_detected'] else _pl(so2['days_detected'], 'día', 'días') + ' con SO2 detectado'}"
                     f" ({so2['days']} días con dato; máximo {_n(so2['max_kt'], 2)} kt).")
    u = r["unrest_end"]["index"]
    if u is not None:
        parts.append(f"El índice de actividad anómala de VolScan cerró el periodo en {_n(u)}/10"
                     + (" (alto: conviene seguimiento estrecho)." if u >= 6 else "."))
    if r["tides"]:
        sig = [k for k, v in r["tides"].items() if v["p_shift"] < 0.05]
        parts.append("Mareas y Luna: " + ("exceso de sismos en la fase de máximo para " + " y ".join(
            "la marea semidiurna" if s == "semidiurnal" else "las mareas vivas" for s in sig) +
            " (correlación a vigilar, no causalidad)." if sig else "sin modulación detectable este mes."))
    parts.append("VolScan no emite niveles de alerta; la valoración oficial corresponde al PEVOLCA.")
    return " ".join(parts)


def available_months(cat: Catalog) -> list[str]:
    if not len(cat):
        return []
    first = dt.datetime.fromtimestamp(cat.t.min(), dt.timezone.utc)
    last = dt.datetime.fromtimestamp(cat.t.max(), dt.timezone.utc)
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out[::-1]
