"""Lateral growth: where a long eruption spreads once the main flow is in place.

WHAT WE LEARNED FROM 2021
-------------------------
The day-by-day validation failed most on days of lateral growth: new lobes,
breakouts from the margins and new vents on the cone's flank (e.g. 9–12 Oct,
25–27 Oct). We tested three ways of adding that to the "where" of the
forecast, each scored against the CEMS maps with the area fixed to the
observed one, so only the location counts:

  share of the new area of the next 72 h that each prior puts in the right cells
    main ensemble (single vent, pre-eruption terrain) ............ 15 %
    + breakout paths from the margins over raised terrain ........ 12 %
    + distance kernel from the active margins .................... 13 %
    infill score (this module) alone ............................. 17 %

None of them predicts the cells well: lateral growth 72 h ahead is close to
unpredictable at 25 m with public data. Mixing them into the building COUNT
made it worse (bias went from −11 % to +16…+33 %), so the count still comes
from the main ensemble.

What DOES help is a watch list. Over the 83 forecasts of 2021, buildings that
some member reaches within 72 h hold about a third of the buildings that were
actually lost, while buildings HEMMED IN by the flow field (infill score
>= 0.2) add another ~20 points of recall, at lower precision. That is a useful
second tier for evacuation planning, and it is how VolScan uses this score.
"""
from __future__ import annotations

import numpy as np


def infill_prior(mask: np.ndarray, valid: np.ndarray, step_m: float, radius_m: float = 400.0, power: float = 3.0) -> np.ndarray:
    """Where lateral growth tends to go: land hemmed in by the flow field (shape = grid, 0 on the flow).

    For each cell outside the flow, count how many of 8 directions meet the
    flow within `radius_m`, and raise the fraction to `power`. Ground between
    two arms of a flow (like Todoque and La Laguna in Oct–Nov 2021) scores
    high; open ground far from the flow scores 0.
    """
    n = max(1, int(radius_m / step_m))
    hit = np.zeros(mask.shape)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        h = np.zeros(mask.shape, bool)
        for s in range(1, n + 1):
            sh = np.zeros_like(mask)
            ys = slice(max(dy * s, 0), mask.shape[0] + min(dy * s, 0))
            yd = slice(max(-dy * s, 0), mask.shape[0] + min(-dy * s, 0))
            xs = slice(max(dx * s, 0), mask.shape[1] + min(dx * s, 0))
            xd = slice(max(-dx * s, 0), mask.shape[1] + min(-dx * s, 0))
            sh[ys, xs] = mask[yd, xd]
            h |= sh
        hit += h
    p = (hit / 8.0) ** power
    p[mask | ~valid] = 0.0
    return p
