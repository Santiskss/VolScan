"""Impact forecasts as CAP 1.2 messages (Common Alerting Protocol, OASIS), the format of 112 and alerting systems.

What goes in each message:
  - status "Exercise": a replay of 2021 or a planning scenario is never a real
    alert, and VolScan never issues real alerts (that is PEVOLCA's job);
  - scope "Restricted", for emergency services only;
  - one <info> in Spanish: event, urgency, severity, certainty, headline, the
    expected impact in numbers, and the instruction to follow the official
    assessment;
  - one <area> per probability band of the lava (polygon, WGS84), plus one
    circle per neighbourhood that could be cut off;
  - <parameter> entries with the figures (buildings, road km, horizon), so a
    machine can read them without parsing text.
Polygons are simplified and capped in points, as some receivers limit them.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import xml.etree.ElementTree as ET

NS = "urn:oasis:names:tc:emergency:cap:1.2"
SENDER = "volscan@tephralabs.es"
MAX_POINTS = 200


def _sub(parent, tag, text=None):
    e = ET.SubElement(parent, f"{{{NS}}}{tag}")
    if text is not None:
        e.text = str(text)
    return e


def _cap_polygon(ring_lonlat: list) -> str | None:
    pts = ring_lonlat
    if len(pts) > MAX_POINTS:
        step = int(len(pts) / MAX_POINTS) + 1
        pts = pts[:-1:step] + [pts[0]]
    if len(pts) < 4:
        return None
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    return " ".join(f"{lat:.5f},{lon:.5f}" for lon, lat in pts)


def certainty_for(p: float) -> str:
    return "Likely" if p >= 0.5 else "Possible" if p >= 0.05 else "Unlikely"


def build(*, kind: str, ref: str, sent: dt.datetime, headline: str, description: str, bands: list[dict],
          isolated: list[dict] | None = None, parameters: dict | None = None, expires: dt.datetime | None = None,
          web: str | None = None) -> bytes:
    """`bands`: GeoJSON features from volscan.geoexport.probability_bands. `isolated`: dicts with name, lon, lat, p_isolated."""
    ET.register_namespace("", NS)
    ident = "volscan-" + hashlib.sha256(f"{kind}|{ref}|{sent.isoformat()}".encode()).hexdigest()[:20]
    a = ET.Element(f"{{{NS}}}alert")
    _sub(a, "identifier", ident)
    _sub(a, "sender", SENDER)
    _sub(a, "sent", sent.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"))
    _sub(a, "status", "Exercise")
    _sub(a, "msgType", "Alert")
    _sub(a, "source", "VolScan (TephraLabs)")
    _sub(a, "scope", "Restricted")
    _sub(a, "restriction", "Solo servicios de emergencia. Simulación o escenario de planificación: NO es una alerta oficial.")
    _sub(a, "note", "Generado por VolScan a partir de datos públicos (IGN, Copernicus EMS, Copernicus DEM, OpenStreetMap). "
                    "La valoración oficial corresponde al PEVOLCA.")
    info = _sub(a, "info")
    _sub(info, "language", "es-ES")
    _sub(info, "category", "Geo")
    _sub(info, "event", "Previsión de impacto de colada de lava")
    _sub(info, "responseType", "Prepare")
    _sub(info, "urgency", "Expected" if kind == "lapalma2021" else "Future")
    _sub(info, "severity", "Severe")
    top = max((b["properties"]["p_min"] for b in bands), default=0.0)
    _sub(info, "certainty", certainty_for(top))
    if expires:
        _sub(info, "expires", expires.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"))
    _sub(info, "senderName", "VolScan · TephraLabs")
    _sub(info, "headline", headline[:160])
    _sub(info, "description", description)
    _sub(info, "instruction", "Seguir las indicaciones del PEVOLCA y del Cabildo. Este mensaje es un ejercicio de apoyo a la "
                              "planificación, no una orden de evacuación.")
    if web:
        _sub(info, "web", web)
    for k, v in (parameters or {}).items():
        p = _sub(info, "parameter")
        _sub(p, "valueName", k)
        _sub(p, "value", v)
    for b in bands:
        ar = _sub(info, "area")
        _sub(ar, "areaDesc", f"Probabilidad de colada {b['properties']['label']} ({b['properties']['area_ha']} ha)")
        for poly in b["geometry"]["coordinates"]:
            s = _cap_polygon(poly[0])           # outer ring only: CAP polygons have no holes
            if s:
                _sub(ar, "polygon", s)
    for it in isolated or []:
        ar = _sub(info, "area")
        _sub(ar, "areaDesc", f"{it['name']}: podría quedar aislado ({round(100 * it['p_isolated'])} %)")
        _sub(ar, "circle", f"{it['lat']:.5f},{it['lon']:.5f} 0.5")
    ET.indent(a)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(a, encoding="utf-8")
