"""Hexagonal Operational Agent for VolScan (Meta Muse Spark / Llama + SAM 3.1 + Physics Engine).

Orchestrates:
1. Retrieval over curated knowledge + live IGN/CEMS data (`volscan.ai.rag`).
2. Deterministic tool-calling over VolScan's physics, assimilation, and CAP 1.2
   engines (`ToolDefinition`).
3. Synthesis via `LanguageModelPort` (Meta Muse Spark, Llama 4, or local Ollama),
   with a deterministic offline synthesizer when no LLM server is reachable so
   emergency operators always receive exact, cited figures.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from typing import Any

from . import rag
from .llm import LLMUnavailable, default_language_model_port
from .ports import LanguageModelPort, LavaSegmentationPort, ToolCall, ToolDefinition, ToolExecutionRecord
from .vision_service import default_segmentation_port, sam3_scene_for_date, sam3_validation_benchmark


def _extract_date(text: str, default: str = "2021-09-25") -> str:
    m = re.search(r"(2021-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    # Match Spanish dates like "20 de septiembre" or "20 sep"
    t = text.lower()
    months = {"sep": "09", "septiembre": "09", "oct": "10", "octubre": "10", "nov": "11", "noviembre": "11", "dic": "12", "diciembre": "12"}
    m2 = re.search(r"\b(\d{1,2})\s*(?:de\s+)?(sep(?:tiembre)?|oct(?:ubre)?|nov(?:iembre)?|dic(?:iembre)?)\b", t)
    if m2:
        day = int(m2.group(1))
        mon = months.get(m2.group(2)[:3], "09")
        return f"2021-{mon}-{day:02d}"
    return default


def _extract_tenerife_branch(text: str) -> str:
    t = text.lower()
    if "pico viejo" in t or "viejo" in t or "chahorra" in t:
        return "pico_viejo"
    if "teide" in t or "blanco" in t:
        return "teide_norte"
    if "noreste" in t or "fasnia" in t or "arafo" in t or "siete fuentes" in t or "güímar" in t or "guimar" in t:
        return "dorsal_noreste"
    if "actual" in t or "sismicidad" in t or "enjambre" in t:
        return "sismicidad_actual"
    return "dorsal_noroeste"


def _extract_zone(text: str) -> str:
    t = text.lower()
    for key, names in (
        ("tenerife", ("tenerife", "teide", "las cañadas", "cañadas")),
        ("la_palma", ("la palma", "cumbre vieja", "tajogaite")),
        ("el_hierro", ("el hierro", "tagoro", "restinga")),
        ("gran_canaria", ("gran canaria",)),
        ("lanzarote", ("lanzarote", "timanfaya")),
        ("fuerteventura", ("fuerteventura",)),
        ("la_gomera", ("la gomera", "gomera")),
        ("enmedio", ("enmedio",)),
    ):
        if any(n in t for n in names):
            return key
    return "all"


def build_domain_tools(seg_port: LavaSegmentationPort | None = None) -> list[ToolDefinition]:
    """Create the 5 deterministic domain tools backed by VolScan's physics and data engines."""
    seg_port = seg_port or default_segmentation_port()

    def tool_canarias_live(zone: str = "all") -> dict[str, Any]:
        from .. import catalog_store as store
        from .. import deformation as D
        from ..seismic import unrest
        from ..zones import BY_KEY, ZONES

        cat = store.load_catalog()
        now_ts = time.time()
        today = dt.datetime.now(dt.timezone.utc).date()
        targets = [BY_KEY[zone]] if zone in BY_KEY and zone != "atlantico" else [z for z in ZONES if z.key != "atlantico"]
        rows = []
        for z in targets:
            zc = store.zone_catalog(cat, z.key)
            u = unrest(zc, now_ts)
            w7 = zc.window(now_ts - 7 * 86400, now_ts)
            w30 = zc.window(now_ts - 30 * 86400, now_ts)
            gnss = D.zone_deformation(z.key, today)
            rows.append(dict(
                zone=z.key,
                name=z.name,
                unrest_index=None if u.index is None else round(u.index, 2),
                n_7d=len(w7),
                n_30d=len(w30),
                max_mag_30d=None if not len(w30) else round(float(w30.mag.max()), 1),
                gnss_level=gnss["level"],
            ))
        return dict(
            evaluated_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            so2=D.so2_status(today),
            zones=rows,
            note="Datos en directo (IGN, NGL, NASA OMPS). El índice (0–10) no es una probabilidad de erupción; alertas oficiales: PEVOLCA.",
        )

    def tool_lapalma_forecast(date: str = "2021-09-25") -> dict[str, Any]:
        from ..datasets import LAPALMA_2021_ONSET
        from ..replay import ImpactReplay, default_replay

        d = dt.date.fromisoformat(date)
        now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
        lp = default_replay()
        ir = ImpactReplay(lp)
        seis = lp.seismic_state(now)
        if now < LAPALMA_2021_ONSET:
            sc = ir.scenario(now)
            return dict(
                date=date,
                phase="pre-eruptive",
                seismic=seis,
                scenario=None if not sc else dict(
                    n_vent_events=sc["n_vent_events"],
                    nearest_candidate_to_real_vent_km=sc["nearest_candidate_to_real_vent_km"],
                    buildings_30d=sc["buildings"],
                    road_km_30d=sc["road_km"],
                    top_places=sc["places"][:5],
                ),
            )
        lava = lp.lava_state(now)
        imp = ir.eruptive(now)
        return dict(
            date=date,
            phase="eruptive",
            seismic=seis,
            observation=lava.get("observation"),
            sea=lava.get("sea"),
            top_places=lava.get("places", [])[:6],
            already_lost=imp.get("already_lost"),
            constrained_72h=imp.get("constrained"),
            unconstrained_72h=dict(buildings=imp.get("buildings"), road_km=imp.get("road_km")),
            watch=dict(high=imp["watch"]["high"], pocket=imp["watch"]["pocket"]) if imp.get("watch") else None,
        )

    def tool_sam3_assimilation(date: str = "2021-09-20") -> dict[str, Any]:
        from ..replay import default_replay

        lp = default_replay()
        if date == "benchmark":
            b = sam3_validation_benchmark()
            return dict(mode="benchmark_22_scenes", summary=b["summary"], adapter=b["adapter"])
        res = sam3_scene_for_date(date, lp=lp, port=seg_port)
        out = {k: v for k, v in res.items() if k != "overlay"}
        return out

    def tool_tenerife_scenario(branch: str = "dorsal_noroeste") -> dict[str, Any]:
        from .. import catalog_store as store
        from ..tenerife import scenario

        sc = scenario(branch, store.load_catalog())
        if not sc or sc.get("unavailable"):
            return dict(branch=branch, unavailable=True, note=sc.get("note") if sc else "escenario desconocido")
        return dict(
            key=sc["key"],
            name=sc["name"],
            history=sc["history"],
            horizon_h=sc["horizon_h"],
            buildings_30d=sc["buildings"],
            road_km_30d=sc["road_km"],
            reach_sea_prob=round(float(sc.get("reach_sea", 0.0)), 3),
            top_places=sc.get("places", [])[:6],
            top_facilities=[dict(name=f["name"], kind=f["kind"], p=f["p"], eta_p50_h=f["eta_h"][1]) for f in sc.get("facilities", [])[:6]],
            isolation=[dict(name=i["name"], p_isolated=i["p_isolated"]) for i in sc.get("isolation", [])[:5]],
            note="Escenario condicional de planificación (no pronóstico de erupción).",
        )

    def tool_cap_alert(target: str = "lapalma2021", ref: str = "2021-09-25") -> dict[str, Any]:
        from .. import cap, catalog_store as store
        from ..geoexport import probability_bands
        from ..replay import ImpactReplay, default_replay
        from ..tenerife import grid as tf_grid, probability_raster, scenario

        now_utc = dt.datetime.now(dt.timezone.utc)
        if target == "tenerife":
            sc = scenario(ref, store.load_catalog())
            if not sc or sc.get("unavailable"):
                return dict(error="Escenario de Tenerife no disponible", target=target, ref=ref)
            p = probability_raster(sc)
            bands = probability_bands(tf_grid(), p) if p is not None else []
            b = sc["buildings"]
            headline = f"Tenerife · escenario {sc['name']} · planificación"
            params = dict(horizonte_h=sc["horizon_h"], edificios_media=round(b["expected"]), vias_km_media=round(sc["road_km"]["expected"], 1))
            xml = cap.build(
                kind="tenerife",
                ref=ref,
                sent=now_utc,
                headline=headline,
                description=f"Escenario {sc['name']}: {round(b['expected'])} edificios de media en 30 d.",
                bands=bands,
                isolated=sc.get("isolation", [])[:5],
                parameters=params,
            )
            return dict(
                standard="OASIS CAP 1.2 (ITU-T X.1303)",
                target=target,
                ref=ref,
                headline=headline,
                n_probability_polygons=len(bands),
                parameters=params,
                xml_bytes=len(xml),
                download_path=f"/api/cap/tenerife/{ref}.xml",
            )

        d = dt.date.fromisoformat(ref)
        now = dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=dt.timezone.utc)
        lp = default_replay()
        ir = ImpactReplay(lp)
        q = ir.coverage_map(now)
        bands = probability_bands(lp.grid, q) if q is not None else []
        imp = ir.eruptive(now)
        c = imp.get("constrained") or {}
        b = c.get("buildings") or imp.get("buildings") or {}
        headline = f"La Palma 2021 · impacto previsto a 72 h ({ref}) · simulación"
        params = dict(
            horizonte_h=72,
            edificios_central=b.get("central", round(b["expected"]) if "expected" in b else None),
            edificios_p10=b.get("low", round(b["p10_p90"][0]) if "p10_p90" in b else None),
            edificios_p90=b.get("high", round(b["p10_p90"][1]) if "p10_p90" in b else None),
        )
        xml = cap.build(
            kind="lapalma2021",
            ref=ref,
            sent=now,
            headline=headline,
            description=f"Reconstrucción {ref}",
            bands=bands,
            isolated=imp.get("isolation", [])[:5],
            expires=now + dt.timedelta(hours=72),
            parameters=params,
        )
        return dict(
            standard="OASIS CAP 1.2 (ITU-T X.1303)",
            target="lapalma2021",
            ref=ref,
            headline=headline,
            n_probability_polygons=len(bands),
            parameters=params,
            xml_bytes=len(xml),
            download_path=f"/api/cap/lapalma2021/{ref}.xml",
        )

    return [
        ToolDefinition(
            name="get_canarias_live_status",
            description="Consulta el estado sísmico en directo (IGN), deformación GNSS (NGL) y SO2 satelital (NASA OMPS) por zona volcánica en Canarias.",
            parameters={
                "type": "object",
                "properties": {
                    "zone": {
                        "type": "string",
                        "description": "Zona volcánica: 'all', 'tenerife', 'la_palma', 'el_hierro', 'gran_canaria', 'lanzarote', 'fuerteventura', 'la_gomera', 'enmedio'.",
                    }
                },
            },
            handler=tool_canarias_live,
        ),
        ToolDefinition(
            name="get_lapalma_2021_forecast",
            description="Consulta la reconstrucción histórica y el pronóstico de impacto a 72 h (edificios, vías, llegada al mar, núcleos) en La Palma 2021 para una fecha AAAA-MM-DD.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Fecha UTC en formato AAAA-MM-DD (entre 2021-09-11 y 2021-12-25)."}
                },
                "required": ["date"],
            },
            handler=tool_lapalma_forecast,
        ),
        ToolDefinition(
            name="run_sam3_satellite_assimilation",
            description="Ejecuta el adaptador Meta SAM 3.1 (LavaSegmentationPort) sobre la imagen térmica satelital SWIR/TIRS en La Palma 2021, asimila la máscara en los 600 recorridos y la compara con Copernicus EMS (usa date='benchmark' para las 22 escenas).",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Fecha AAAA-MM-DD o 'benchmark' para el resumen de las 22 escenas EMSR546."}
                },
                "required": ["date"],
            },
            handler=tool_sam3_assimilation,
        ),
        ToolDefinition(
            name="simulate_tenerife_scenario",
            description="Ejecuta o consulta un escenario condicional de impacto a 30 días en Tenerife (bocas históricas o sismicidad actual).",
            parameters={
                "type": "object",
                "properties": {
                    "branch": {
                        "type": "string",
                        "enum": ["dorsal_noroeste", "pico_viejo", "teide_norte", "dorsal_noreste", "sismicidad_actual"],
                        "description": "Rama del sistema volcánico de Tenerife.",
                    }
                },
                "required": ["branch"],
            },
            handler=tool_tenerife_scenario,
        ),
        ToolDefinition(
            name="preview_cap_112_alert",
            description="Genera y previsualiza el mensaje estándar de alerta OASIS CAP 1.2 XML para 112 Canarias / ES-Alert.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["lapalma2021", "tenerife"]},
                    "ref": {"type": "string", "description": "Fecha AAAA-MM-DD (para lapalma2021) o rama (para tenerife)."},
                },
                "required": ["target", "ref"],
            },
            handler=tool_cap_alert,
        ),
    ]


def infer_deterministic_tool_calls(question: str, context: str | None = None) -> list[ToolCall]:
    """Deterministic intent router so the agent always runs the right physics/data tools even if a local LLM omits tool_calls."""
    q = question.lower()
    calls: list[ToolCall] = []
    ctx_date = context.split(":", 1)[1] if (context and context.startswith("lapalma2021:")) else "2021-09-25"
    date_str = _extract_date(question, default=ctx_date)

    if any(w in q for w in ("sam", "sam 3", "sam3", "segmenta", "satélite térmica", "termica", "iou", "meta sam")):
        arg = "benchmark" if any(w in q for w in ("22", "validación", "validacion", "media", "global", "benchmark")) and not re.search(r"2021-\d{2}-\d{2}", question) else date_str
        calls.append(ToolCall(id="det_sam3", name="run_sam3_satellite_assimilation", arguments={"date": arg}))

    if any(w in q for w in ("cap", "112", "es-alert", "xml", "alerta estándar")):
        if "tenerife" in q or "garachico" in q or "dorsal" in q or "teide" in q:
            calls.append(ToolCall(id="det_cap", name="preview_cap_112_alert", arguments={"target": "tenerife", "ref": _extract_tenerife_branch(question)}))
        else:
            calls.append(ToolCall(id="det_cap", name="preview_cap_112_alert", arguments={"target": "lapalma2021", "ref": date_str}))

    if any(w in q for w in ("tenerife", "garachico", "icod", "chinyero", "pico viejo", "dorsal", "siete fuentes", "fasnia", "arafo", "güímar", "guimar")):
        calls.append(ToolCall(id="det_tf", name="simulate_tenerife_scenario", arguments={"branch": _extract_tenerife_branch(question)}))

    if any(w in q for w in ("la palma", "tajogaite", "todoque", "colada", "edificios", "mar", "2021", "72 h", "72h")) or (context and context.startswith("lapalma2021:")):
        calls.append(ToolCall(id="det_lp", name="get_lapalma_2021_forecast", arguments={"date": date_str}))

    if any(w in q for w in ("hoy", "directo", "actual", "enjambre", "canarias", "el hierro", "gnss", "so2", "índice", "indice")) or context == "canarias" or not calls:
        calls.append(ToolCall(id="det_live", name="get_canarias_live_status", arguments={"zone": _extract_zone(question)}))

    return calls[:3]


def _synthesize_offline(question: str, records: list[ToolExecutionRecord], hits) -> str:
    """Deterministic, zero-hallucination Spanish response synthesized directly from executed tool outputs and RAG chunks."""
    parts: list[str] = []
    for rec in records:
        out = rec.output
        if rec.name == "run_sam3_satellite_assimilation":
            if out.get("mode") == "benchmark_63_scenes" or "summary" in out:
                s = out["summary"]
                parts.append(
                    f"Segmentación satelital con Meta SAM 3.1 (63 cartografías EMSR546 en La Palma 2021): "
                    f"IoU medio {s['mean_iou']} (mediana {s['median_iou']}, precisión {s['mean_precision']}, exhaustividad {s['mean_recall']}), "
                    f"latencia media {s['mean_latency_ms']} ms por escena y ganancia de antelación operativa de +{s['lead_time_gain_h']} h frente a las 24 h de fotointerpretación manual."
                )
            elif out.get("available"):
                c = out["comparison_vs_cems"]
                af = out["assimilated_forecast"]
                eta = af["sea_eta_h"]
                eta_str = f"P50 {eta[1]} h (P10–P90 {eta[0]}–{eta[2]} h)" if eta and eta[1] is not None else "sin llegada prevista en el horizonte"
                parts.append(
                    f"Asimilación satelital Meta SAM 3.1 ({out['date']}): superficie segmentada {c['sam3_area_ha']} ha frente a {c['cems_area_ha']} ha de Copernicus EMS "
                    f"(IoU {c['iou']}, alcance {c['sam3_reach_m']} m vs {c['cems_reach_m']} m, +{out['lead_time_advantage_h']} h de antelación). "
                    f"Tras reponderar los 600 recorridos con la máscara SAM 3.1 (ESS {af['ess']}), la probabilidad de llegada al mar es {round(100 * af['sea_p_ever'])} % ({eta_str})."
                )
        elif rec.name == "get_lapalma_2021_forecast":
            if out.get("phase") == "pre-eruptive":
                sc = out.get("scenario")
                if sc:
                    b = sc["buildings_30d"]
                    parts.append(
                        f"Reconstrucción pre-eruptiva ({out['date']}): escenario desde {sc['n_vent_events']} sismos someros "
                        f"(candidato más cercano a {sc['nearest_candidate_to_real_vent_km']} km de la boca real de Tajogaite). "
                        f"Impacto condicional a 30 d: {round(b['expected'])} edificios de media (P10–P90 {round(b['p10_p90'][0])}–{round(b['p10_p90'][1])})."
                    )
            else:
                sea = out.get("sea") or {}
                c = out.get("constrained_72h")
                if c:
                    b, r = c["buildings"], c["road_km"]
                    parts.append(
                        f"La Palma 2021 ({out['date']}, reconstrucción histórica): en las próximas 72 h se pronostican {b['central']} edificios nuevos "
                        f"(P10–P90 {b['low']}–{b['high']}) y {r['central']} km de vías ({r['low']}–{r['high']} km). "
                        f"Probabilidad de alcanzar el mar: {round(100 * sea.get('p_ever', 0))} %."
                    )
                else:
                    b = (out.get("unconstrained_72h") or {}).get("buildings") or {}
                    parts.append(
                        f"La Palma 2021 ({out['date']}, antes del primer mapa Copernicus entregado): conjunto inicial desde la boca con "
                        f"probabilidad de llegar al mar del {round(100 * sea.get('p_ever', 0))} % y {round(b.get('expected', 0))} edificios esperados en 72 h."
                    )
        elif rec.name == "simulate_tenerife_scenario":
            if not out.get("unavailable"):
                b, r = out["buildings_30d"], out["road_km_30d"]
                top_p = ", ".join(f"{p['name']} ({round(100 * p['p'])} %)" for p in out.get("top_places", [])[:3])
                parts.append(
                    f"Escenario de planificación en Tenerife «{out['name']}» ({out['history']}): en 30 días alcanzaría {round(b['expected'])} edificios de media "
                    f"(P10–P90 {round(b['p10_p90'][0])}–{round(b['p10_p90'][1])}) y {round(r['expected'], 1)} km de vías, con {round(100 * out['reach_sea_prob'])} % de recorridos llegando al mar. "
                    f"Núcleos más expuestos: {top_p}."
                )
        elif rec.name == "preview_cap_112_alert":
            parts.append(
                f"Mensaje interoperable {out.get('standard')}: «{out.get('headline')}» con {out.get('n_probability_polygons')} polígonos de probabilidad "
                f"({out.get('xml_bytes')} bytes XML, descargable en {out.get('download_path')})."
            )
        elif rec.name == "get_canarias_live_status":
            zs = out.get("zones") or []
            if zs:
                top_z = sorted(zs, key=lambda z: (z["unrest_index"] or -1, z["n_7d"]), reverse=True)[:3]
                z_txt = "; ".join(f"{z['name']}: índice {z['unrest_index'] if z['unrest_index'] is not None else '—'}/10 ({z['n_7d']} sismos/7d, GNSS {z['gnss_level']})" for z in top_z)
                parts.append(f"Vigilancia en directo en Canarias ({out['evaluated_at']}): {z_txt}.")

    if hits:
        parts.append(f"Referencias documentales consultadas: [1] {hits[0][0].doc} ({hits[0][0].section}).")
    parts.append("Nota: VolScan es una herramienta de apoyo a la decisión; las alertas oficiales corresponden exclusivamente al PEVOLCA.")
    return "\n\n".join(parts)


class VolScanAgent:
    """Hexagonal Application Service orchestrating `LanguageModelPort`, `LavaSegmentationPort`, RAG, and domain tools."""

    def __init__(
        self,
        llm_port: LanguageModelPort | None = None,
        seg_port: LavaSegmentationPort | None = None,
    ):
        self.llm_port = llm_port or default_language_model_port()
        self.seg_port = seg_port or default_segmentation_port()
        self.tools = build_domain_tools(self.seg_port)
        self._tool_map = {t.name: t for t in self.tools}

    def status(self) -> dict[str, Any]:
        return dict(
            architecture="hexagonal-ports-and-adapters",
            llm_port=self.llm_port.status(),
            segmentation_port=self.seg_port.status(),
            registered_tools=[dict(name=t.name, description=t.description) for t in self.tools],
        )

    def _execute_calls(self, calls: list[ToolCall]) -> list[ToolExecutionRecord]:
        records: list[ToolExecutionRecord] = []
        seen: set[str] = set()
        for c in calls:
            key = f"{c.name}:{json.dumps(c.arguments, sort_keys=True)}"
            if key in seen or c.name not in self._tool_map:
                continue
            seen.add(key)
            t0 = time.perf_counter()
            try:
                out = self._tool_map[c.name].handler(**c.arguments)
            except Exception as e:
                out = dict(error=f"{type(e).__name__}: {e}")
            dt_ms = (time.perf_counter() - t0) * 1000.0
            records.append(ToolExecutionRecord(name=c.name, arguments=c.arguments, output=out, duration_ms=round(dt_ms, 1)))
        return records

    def run(self, question: str, context: str | None = None, events=None, lava_obs=None) -> dict[str, Any]:
        idx = rag.get_index(events, lava_obs)
        hits = idx.search(question, k=5)

        # Step 1: Determine deterministic tools & optional native LLM tool calls
        det_calls = infer_deterministic_tool_calls(question, context)
        records = self._execute_calls(det_calls)

        tool_summary_for_prompt = {
            r.name: dict(arguments=r.arguments, result=r.output) for r in records
        }
        messages = rag.build_prompt(question, hits, live=tool_summary_for_prompt)

        try:
            turn = self.llm_port.complete(messages, tools=self.tools, temperature=0.2, max_tokens=700)
            # If the model requested additional tool calls not yet in `records`, execute them and complete synthesis
            if turn.tool_calls:
                extra_records = self._execute_calls(turn.tool_calls)
                if extra_records:
                    records.extend(extra_records)
                    combined = {r.name: dict(arguments=r.arguments, result=r.output) for r in records}
                    messages = rag.build_prompt(question, hits, live=combined)
                    turn = self.llm_port.complete(messages, tools=None, temperature=0.2, max_tokens=700)

            answer = turn.content or _synthesize_offline(question, records, hits)
            return dict(
                answer=answer,
                ai=bool(turn.content),
                model=turn.public_model(),
                segmentation_adapter=self.seg_port.status(),
                tool_calls=[
                    dict(name=r.name, arguments=r.arguments, duration_ms=r.duration_ms, output=r.output)
                    for r in records
                ],
                citations=rag.cite(hits),
            )
        except LLMUnavailable as e:
            fallback_text = _synthesize_offline(question, records, hits)
            st = self.llm_port.status()
            return dict(
                answer=fallback_text,
                ai=False,
                error=str(e),
                model=st,
                segmentation_adapter=self.seg_port.status(),
                tool_calls=[
                    dict(name=r.name, arguments=r.arguments, duration_ms=r.duration_ms, output=r.output)
                    for r in records
                ],
                citations=rag.cite(hits),
            )
