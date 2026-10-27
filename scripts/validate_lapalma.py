#!/usr/bin/env python3
"""Recompute the La Palma 2021 validation (out/cache/validation_lapalma2021.json), with a sensitivity to the
delay between image acquisition and map delivery (CEMS: 7 h fast mode, up to 48 h standard mode).

Usage: python scripts/validate_lapalma.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from volscan.api.app import _clean  # noqa: E402
from volscan.replay import CACHE, DELIVERY_DELAY_H, ImpactReplay, LaPalma2021, validation_payload, validation_summary  # noqa: E402


def main():
    sens = {}
    for h in (7.0, 48.0):
        ir = ImpactReplay(LaPalma2021(catalog=None, delivery_delay_h=h))
        s = validation_summary(ir.validation())
        sens[str(int(h))] = {k: s[k] for k in ("days", "within_p10_p90_72h", "bias_pct", "mae_72")}
        print(f"delay {h:.0f} h:", sens[str(int(h))])
    ir = ImpactReplay(LaPalma2021(catalog=None, delivery_delay_h=DELIVERY_DELAY_H))
    res = _clean(validation_payload(ir, sens))
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "validation_lapalma2021.json").write_text(json.dumps(res))
    print(f"delay {DELIVERY_DELAY_H:.0f} h:", res["summary"])


if __name__ == "__main__":
    main()
