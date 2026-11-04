"""PDF and CSV exports: the monthly report and the impact sheet, ready to file or attach to an emergency plan.

PDF is drawn with reportlab and the standard Helvetica font (no font files to
ship). Figures and wording come from the same dictionaries the web app shows,
so the PDF never says something the screen doesn't.
"""
from __future__ import annotations

import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = colors.HexColor("#b4532f")
INK = colors.HexColor("#1d1b18")
MUTED = colors.HexColor("#6f675b")
LINE = colors.HexColor("#d9d1c0")
PAPER = colors.HexColor("#fbf8f2")

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=INK, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, textColor=INK, spaceBefore=10, spaceAfter=4)
KICK = ParagraphStyle("k", parent=_ss["Normal"], fontName="Helvetica", fontSize=8, textColor=ACCENT, leading=10)
BODY = ParagraphStyle("b", parent=_ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK)
SMALL = ParagraphStyle("s", parent=BODY, fontSize=7.8, leading=10.5, textColor=MUTED)


def _t(s) -> str:
    """Text safe for Helvetica (WinAnsi) and for reportlab's mini-markup."""
    s = "—" if s is None else str(s)
    s = s.replace("≥", ">=").replace("≤", "<=").replace("→", "->").replace("×", "x").replace("−", "-")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _n(v, d: int = 1) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int,)) or (isinstance(v, float) and d == 0):
        return f"{round(v):,}"
    return f"{v:.{d}f}"


def _table(rows, widths, header=True):
    t = Table([[Paragraph(_t(c), BODY if not (header and i == 0) else SMALL) for c in r] for i, r in enumerate(rows)],
              colWidths=widths, repeatRows=1 if header else 0)
    st = [("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st.append(("LINEBELOW", (0, 0), (-1, 0), 0.8, INK))
    t.setStyle(TableStyle(st))
    return t


def _bars(values, width=170 * mm, height=38 * mm, label=""):
    vals = [0 if v is None else float(v) for v in values]
    mx = max(vals + [1.0])
    d = Drawing(width, height)
    n = max(1, len(vals))
    bw = (width - 30) / n
    d.add(Line(28, 12, width, 12, strokeColor=LINE, strokeWidth=0.5))
    for i, v in enumerate(vals):
        h = (height - 26) * v / mx
        d.add(Rect(30 + i * bw + 0.6, 12, max(0.6, bw - 1.2), h, fillColor=ACCENT, strokeColor=None))
    d.add(String(0, height - 8, label, fontName="Helvetica", fontSize=7.5, fillColor=MUTED))
    d.add(String(0, height - 18, _n(mx, 0), fontName="Helvetica", fontSize=7, fillColor=MUTED))
    d.add(String(30, 2, "1", fontName="Helvetica", fontSize=7, fillColor=MUTED))
    d.add(String(width - 10, 2, str(n), fontName="Helvetica", fontSize=7, fillColor=MUTED))
    return d


def _doc(story, title: str) -> bytes:
    buf = io.BytesIO()

    def footer(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawString(18 * mm, 10 * mm, "VolScan · TephraLabs · not an official alert: the assessment belongs to PEVOLCA")
        c.drawRightString(192 * mm, 10 * mm, f"p. {doc.page}")
        c.restoreState()

    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                      title=title, author="VolScan (TephraLabs)").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ---------------------------------------------------------------- monthly report
def report_pdf(r: dict) -> bytes:
    s = r["stats"]
    story = [Paragraph("MONTHLY VOLCANO MONITORING REPORT · VOLSCAN", KICK),
             Paragraph(_t(r["title"] + (" (current month)" if r["partial"] else "")), H1),
             Paragraph(_t(f"Generated {r['generated_at'][:16].replace('T', ' ')} UTC · zone: {r['zone']['note'] or r['zone']['name']}"), SMALL),
             Spacer(1, 6), Paragraph(_t(r["summary"]), BODY), Paragraph("Figures for the month", H2),
             _table([["Indicator", "This month", "Previous month"],
                     ["Earthquakes", _n(s["n"], 0), _n(r["prev"]["n"], 0)],
                     ["Maximum magnitude", _n(s["max_mag"]), _n(r["prev"]["max_mag"])],
                     ["M >= 3", _n(s["n_m3"], 0), _n(r["prev"]["n_m3"], 0)],
                     ["Median depth (km)", _n(s["depth_median"]), _n(r["prev"]["depth_median"])],
                     ["Earthquakes shallower than 5 km", _n(s["shallow_lt5"], 0), _n(r["prev"]["shallow_lt5"], 0)],
                     ["Rate vs 12-month mean", f"x{_n(r['rate_ratio'])}", ""],
                     ["Unrest index at close (0-10)", _n(r["unrest_end"]["index"]), ""],
                     ["b-value", f"{_n(r['b']['b'], 2)} ± {_n(r['b']['sigma'], 2)}" if r.get("b") else "too few data", ""]],
                    [80 * mm, 45 * mm, 45 * mm]),
             Spacer(1, 6), _bars(r["daily"], label="Earthquakes per day")]
    dfm = r.get("deformation")
    story.append(Paragraph("Deformation (GNSS)", H2))
    if dfm:
        story.append(_table([["Station", "Vertical (mm)", "z horiz. / vert.", "Level", "Data up to"]] +
                            [[x["code"] + " · " + x["place"], _n(x.get("anom_u_mm")), f"{_n(x.get('z_h'))} / {_n(abs(x.get('z_u') or 0))}",
                              x["level"], x.get("evaluated_at") or x["last"]] for x in dfm["stations"]],
                            [52 * mm, 28 * mm, 32 * mm, 26 * mm, 32 * mm]))
    else:
        story.append(Paragraph("No public GNSS stations with data for this month.", SMALL))
    story.append(Paragraph("Gas (satellite SO2)", H2))
    so2 = r.get("so2")
    story.append(Paragraph(_t(f"{so2['days_detected']} of {so2['days']} days with SO2 >= {_n(so2['threshold_kt'], 0)} kt; daily maximum "
                              f"{_n(so2['max_kt'], 2)} kt.") if so2 else "No SO2 data for this month.", BODY))
    story += [Paragraph("Most notable earthquakes", H2),
              _table([["Date (UTC)", "M", "Depth (km)", "Int.", "Place"]] +
                     [[e["t"][:16].replace("T", " "), _n(e["mag"]), _n(e["depth"]), e["int_max"] or "—", e["place"]] for e in r["top_events"]],
                     [34 * mm, 14 * mm, 20 * mm, 14 * mm, 88 * mm]),
              Spacer(1, 8), Paragraph(_t("Sources: " + " · ".join(r["sources"])), SMALL)]
    return _doc(story, r["title"])


def report_csv(r: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["zona", "mes", "dia", "terremotos", "profundidad_mediana_km"])
    for i, (n, d) in enumerate(zip(r["daily"], r["daily_depth"]), start=1):
        w.writerow([r["zone"]["key"], r["month"], i, n, "" if d is None else round(d, 2)])
    w.writerow([])
    w.writerow(["destacados_fecha_utc", "magnitud", "tipo", "profundidad_km", "intensidad", "lugar", "id_ign"])
    for e in r["top_events"]:
        w.writerow([e["t"], e["mag"], e["mag_type"], e["depth"], e["int_max"] or "", e["place"], e["id"]])
    return ("﻿" + out.getvalue()).encode("utf-8")          # BOM so Excel reads the accents


# ---------------------------------------------------------------- impact sheet
def impact_pdf(title: str, subtitle: str, kpis: list[tuple[str, str, str]], facilities: list[dict], isolation: list[dict],
               places: list[dict], method: str, sources: str) -> bytes:
    story = [Paragraph("IMPACT REPORT · VOLSCAN", KICK), Paragraph(_t(title), H1), Paragraph(_t(subtitle), SMALL), Spacer(1, 6),
             _table([["Indicador", "Valor", "Rango / nota"]] + [list(k) for k in kpis], [62 * mm, 40 * mm, 68 * mm])]
    if places:
        story += [Paragraph("Reachable neighbourhoods", H2),
                  _table([["Neighbourhood", "Probability"]] + [[p["name"], f"{round(100 * p['p'])} %"] for p in places[:15]], [120 * mm, 50 * mm])]
    if isolation:
        story += [Paragraph("Neighbourhoods that could be cut off", H2),
                  _table([["Neighbourhood", "Reached", "Isolated"]] +
                         [[i["name"], f"{round(100 * i['p_reached'])} %", f"{round(100 * i['p_isolated'])} %"] for i in isolation[:15]],
                         [100 * mm, 35 * mm, 35 * mm])]
    if facilities:
        story += [Paragraph("Services and infrastructure", H2),
                  _table([["Service", "Name", "P", "Arrival P50"]] +
                         [[f["kind"], f["name"], "LOST" if f.get("already_lost") else f"{round(100 * f['p'])} %",
                           "" if f.get("already_lost") or f["eta_h"][1] is None else _hours(f["eta_h"][1])] for f in facilities[:25]],
                         [40 * mm, 80 * mm, 22 * mm, 28 * mm])]
    story += [Spacer(1, 8), Paragraph(_t("Method: " + method), SMALL), Paragraph(_t("Sources: " + sources), SMALL)]
    return _doc(story, title)


def _hours(h: float) -> str:
    return f"{round(h)} h" if h < 48 else f"{h / 24:.1f} d"


def impact_csv(facilities: list[dict], isolation: list[dict]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["tipo", "nombre", "lon", "lat", "probabilidad", "ya_perdido", "llegada_p10_h", "llegada_p50_h", "llegada_p90_h"])
    for f in facilities:
        w.writerow([f["kind"], f["name"], f["lon"], f["lat"], f["p"], f.get("already_lost", False), *f["eta_h"]])
    w.writerow([])
    w.writerow(["nucleo", "lon", "lat", "p_alcanzado", "p_aislado"])
    for i in isolation:
        w.writerow([i["name"], i["lon"], i["lat"], i["p_reached"], i["p_isolated"]])
    return ("﻿" + out.getvalue()).encode("utf-8")
