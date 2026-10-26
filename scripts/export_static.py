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
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"snapshot in {out}: {sum(1 for _ in out.rglob('*.json'))} JSON, {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "static"))
