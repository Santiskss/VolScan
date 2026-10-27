#!/usr/bin/env python3
"""Static snapshot of VolScan: precomputes every API response into JSON files next to the web build.

It lets you look at the atlas without a server, for example as a private
claude.ai page to share with the team. The AI assistant isn't included: it
needs a model, and runs in the local version (VolScan.command). The
"situation report" for each day in the snapshot is the numeric summary,
clearly labelled as such.

Usage: python scripts/export_static.py out/static   (after `VITE_STATIC=1 npm run build` in web/)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from volscan.api import app as A  # noqa: E402


def main(out: Path):
    dist = ROOT / "web" / "dist"
    if not (dist / "index.html").exists():
        sys.exit("build the web first: (cd web && VITE_STATIC=1 npm run build)")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(dist, out)
    c = TestClient(A.app)

    def save(path: str, url: str, method: str = "get"):
        r = c.post(url, json={}) if method == "post" else c.get(url)
        r.raise_for_status()
        f = out / f"{path}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(r.text)
        return r.json()

    status = save("api/status", "/api/status")
    status["llm"] = dict(ok=False, provider="local", model="—")
    (out / "api/status.json").write_text(json.dumps(status))
    save("api/terrain/lapalma", "/api/terrain/lapalma")
    save("api/terrain/archipelago", "/api/terrain/archipelago")
    save("api/canarias/zones", "/api/canarias/zones")
    save("api/canarias/calibration", "/api/canarias/calibration")
    for z in ("tenerife", "la_palma", "el_hierro", "la_gomera", "enmedio", "gran_canaria", "lanzarote_fuerteventura"):
        save(f"api/canarias/indicators/{z}", f"/api/canarias/indicators?zone={z}")
    for d in (7, 30, 90, 365):
        save(f"api/canarias/quakes-{d}", f"/api/canarias/quakes?days={d}")
    for z in ("la_palma", "el_hierro", "tenerife", "gran_canaria", "lanzarote_fuerteventura"):
        save(f"api/solunar/{z}", f"/api/solunar?zone={z}&start=2011-01-01")
    meta = save("api/lapalma2021/meta", "/api/lapalma2021/meta")
    save("api/lapalma2021/quakes", "/api/lapalma2021/quakes")
    for day in meta["days"]:
        d = save(f"api/lapalma2021/day/{day}", f"/api/lapalma2021/day/{day}")
        brief = dict(date=day, text=A._fallback_brief(d), ai=False, model=dict(provider="local", model="—"),
                     error="instantánea estática", citations=[])
        (out / f"api/lapalma2021/briefing-static/{day}.json").parent.mkdir(parents=True, exist_ok=True)
        (out / f"api/lapalma2021/briefing-static/{day}.json").write_text(json.dumps(brief, ensure_ascii=False))
    for day in meta["days"]:
        save(f"api/lapalma2021/impact/{day}", f"/api/lapalma2021/impact/{day}")
    save("api/lapalma2021/validation", "/api/lapalma2021/validation")
    months_all = c.get("/api/reports/months").json()
    recent = months_all["months"][:6]
    keep = recent + ["2021-12", "2021-11", "2021-10", "2021-09", "2011-12", "2011-11", "2011-10", "2011-09", "2011-08", "2011-07"]
    months_all["months"] = keep
    (out / "api/reports/months.json").parent.mkdir(parents=True, exist_ok=True)
    (out / "api/reports/months.json").write_text(json.dumps(months_all))
    for z in months_all["zones"]:
        for m in keep:
            save(f"api/reports/monthly/{z['key']}/{m}", f"/api/reports/monthly?zone={z['key']}&month={m}")
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"snapshot in {out}: {sum(1 for _ in out.rglob('*.json'))} JSON, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "static"))
