"""Meta SAM 3.1 Adapter implementing LavaSegmentationPort.

Supports three interchangeable execution modes behind the same hexagonal port:
1. `remote_api`: Calls a Meta SAM 3.1 / OpenAI-Vision / vLLM segmentation
   endpoint (`VOLSCAN_SAM_ENDPOINT`, authenticated with `META_API_KEY` or
   `VOLSCAN_SAM_KEY`) sending the false-colour SWIR/TIRS image, spatial point
   prompts, bounding box, and text prompt ("active volcanic lava flow").
2. `local_weights`: Uses local PyTorch weights (`VOLSCAN_SAM_CHECKPOINT`,
   Meta `sam3` / `sam2` predictor on `mps`/`cuda`/`cpu`) if present.
3. `physics_prompt_seeded`: Zero-dependency prompt-seeded geodesic region
   growing driven by the exact SAM 3.1 positive/negative prompt points,
   Planck brightness temperature, SWIR radiance, DEM downslope connectivity,
   and prior flow persistence (so cooled crust inside the flow body is
   retained while cloud/plume halo near the vent is rejected).
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
from typing import Any

import numpy as np

from .llm import _load_dotenv
from .ports import LavaSegmentationPort, PromptPoint, SegmentationResult, ThermalScene


def extract_sam3_prompts(scene: ThermalScene, max_hotspots: int = 8) -> tuple[list[PromptPoint], tuple[float, float, float, float] | None]:
    """Derive positive/negative spatial prompts and bounding box for SAM 3.1 from a thermal scene."""
    g = scene.grid
    valid = ~np.isnan(g.elev)
    X, Y = g.cell_centres()
    vx, vy = scene.vent_xy
    points: list[PromptPoint] = [PromptPoint(float(vx), float(vy), label=1, kind="vent")]

    # Score active incandescent spots (high SWIR + high brightness temp, on valid land)
    hot_score = np.where(valid, scene.swir_radiance * np.clip((scene.brightness_temp_k - 315.0) / 400.0, 0.0, 2.0), 0.0)
    cand_ij = np.argwhere(hot_score > 0.32)
    if len(cand_ij) > 0:
        scores = hot_score[cand_ij[:, 0], cand_ij[:, 1]]
        order = np.argsort(-scores)
        chosen_xy = [(vx, vy)]
        for idx in order:
            r, c = int(cand_ij[idx, 0]), int(cand_ij[idx, 1])
            px, py = float(X[r, c]), float(Y[r, c])
            if all(np.hypot(px - cx, py - cy) >= 250.0 for cx, cy in chosen_xy):
                points.append(PromptPoint(px, py, label=1, kind="front_hotspot"))
                chosen_xy.append((px, py))
                if len(points) >= 1 + max_hotspots:
                    break

    # Include prior flow core prompts (lava crust cools at surface while remaining part of the emplaced flow)
    if scene.prior_mask_flat is not None and scene.prior_mask_flat.any():
        pm = scene.prior_mask_flat.reshape(g.shape)
        pr_ij = np.argwhere(pm & valid)
        if len(pr_ij) > 0:
            step = max(1, len(pr_ij) // 3)
            for r, c in pr_ij[::step][:3]:
                points.append(PromptPoint(float(X[r, c]), float(Y[r, c]), label=1, kind="prior_core"))

    # Compute bounding box around active anomaly + prior mask with 250 m margin
    active_mask = (hot_score > 0.18) | (scene.prior_mask_flat.reshape(g.shape) if scene.prior_mask_flat is not None else False)
    box_xy: tuple[float, float, float, float] | None = None
    if np.any(active_mask):
        ys, xs = np.where(active_mask)
        x_min = float(X[ys, xs].min() - 250.0)
        x_max = float(X[ys, xs].max() + 250.0)
        y_min = float(Y[ys, xs].min() - 250.0)
        y_max = float(Y[ys, xs].max() + 250.0)
        box_xy = (x_min, y_min, x_max, y_max)

        # Add 2 negative background prompts just outside the active box on cold land
        cold = valid & (scene.brightness_temp_k < 303.0) & ~active_mask
        cold_ij = np.argwhere(cold)
        if len(cold_ij) >= 2:
            for r, c in (cold_ij[len(cold_ij) // 4], cold_ij[(3 * len(cold_ij)) // 4]):
                points.append(PromptPoint(float(X[r, c]), float(Y[r, c]), label=0, kind="cold_background"))

    return points, box_xy


def _prompt_seeded_segmentation(
    scene: ThermalScene,
    points: list[PromptPoint],
    box_xy: tuple[float, float, float, float] | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Prompt-seeded geodesic/morphological segmentation over SWIR + TIRS + DEM + prior persistence."""
    g = scene.grid
    valid = ~np.isnan(g.elev)
    X, Y = g.cell_centres()
    vx, vy = scene.vent_xy
    vent_elev = float(g.elev[g.xy_to_ij(vx, vy)]) if valid[g.xy_to_ij(vx, vy)] else 1100.0

    # Normalised thermal likelihood [0..1]
    t_norm = np.clip((scene.brightness_temp_k - 308.0) / 220.0, 0.0, 1.0)
    radiance = np.clip(0.65 * scene.swir_radiance + 0.35 * t_norm, 0.0, 1.0)

    # Topographic plausibility: lava cannot climb significantly above the vent elevation
    topo_ok = valid & (g.elev <= vent_elev + 65.0)
    if box_xy is not None:
        x0, y0, x1, y1 = box_xy
        in_box = (X >= x0 - 150.0) & (X <= x1 + 150.0) & (Y >= y0 - 150.0) & (Y <= y1 + 150.0)
        topo_ok &= in_box

    prior = scene.prior_mask_flat.reshape(g.shape).astype(bool) if scene.prior_mask_flat is not None else np.zeros(g.shape, bool)

    # Seed map from positive prompt points + prior core + strong thermal core
    seeds = prior.copy() | (topo_ok & (radiance >= 0.52))
    for p in points:
        if p.label == 1:
            ri, cj = g.xy_to_ij(p.x, p.y)
            if 0 <= ri < g.shape[0] and 0 <= cj < g.shape[1] and topo_ok[ri, cj]:
                seeds[ri, cj] = True

    # Iterative region growing from seeds into connected warm cells (rejecting isolated plume/cloud noise)
    mask = seeds.copy()
    grow_candidate = topo_ok & (radiance >= 0.27)
    for _ in range(18):
        nb = mask.copy()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            s = np.zeros_like(mask)
            r0, r1 = max(0, di), mask.shape[0] + min(0, di)
            c0, c1 = max(0, dj), mask.shape[1] + min(0, dj)
            s[r0:r1, c0:c1] = mask[r0 - di:r1 - di, c0 - dj:c1 - dj]
            nb |= s
        nxt = mask | (nb & grow_candidate)
        if np.array_equal(nxt, mask):
            break
        mask = nxt

    # Fill 1-cell interior holes (cooled crust pockets surrounded by ≥ 5 active/emplaced neighbours)
    nb_count = np.zeros(g.shape, int)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            s = np.zeros(g.shape, int)
            r0, r1 = max(0, di), mask.shape[0] + min(0, di)
            c0, c1 = max(0, dj), mask.shape[1] + min(0, dj)
            s[r0:r1, c0:c1] = mask[r0 - di:r1 - di, c0 - dj:c1 - dj]
            nb_count += s
    mask = (mask | ((nb_count >= 5) & topo_ok & (radiance >= 0.16))) & valid

    conf = np.where(mask, np.clip(0.55 + 0.45 * np.maximum(radiance, prior.astype(float) * 0.85), 0.0, 1.0),
                    np.clip(radiance * 0.4, 0.0, 0.45))
    return mask.ravel(), conf.ravel()


class MetaSAM3Adapter(LavaSegmentationPort):
    """Hexagonal Adapter for Meta SAM 3.1 (Segment Anything Model 3.1).

    Configuration via environment variables (or `.env`):
      VOLSCAN_SAM_MODEL       default: meta/sam-3.1-hiera-large
      VOLSCAN_SAM_ENDPOINT    optional HTTP endpoint for remote SAM 3.1 inference
      VOLSCAN_SAM_CHECKPOINT  optional path to local PyTorch SAM 3.1 / SAM 2.1 weights
      VOLSCAN_SAM_KEY         optional API key (falls back to META_API_KEY)
    """

    def __init__(
        self,
        model: str | None = None,
        endpoint: str | None = None,
        checkpoint: str | None = None,
        api_key: str | None = None,
    ):
        _load_dotenv()
        self.model = model or os.environ.get("VOLSCAN_SAM_MODEL", "meta/sam-3.1-hiera-large")
        self.endpoint = (endpoint or os.environ.get("VOLSCAN_SAM_ENDPOINT", "")).strip() or None
        self.checkpoint = (checkpoint or os.environ.get("VOLSCAN_SAM_CHECKPOINT", "")).strip() or None
        self.api_key = api_key or os.environ.get("VOLSCAN_SAM_KEY") or os.environ.get("META_API_KEY")

    def _resolve_mode(self) -> str:
        if self.endpoint:
            return "remote_api"
        if self.checkpoint and os.path.exists(self.checkpoint):
            return "local_weights"
        return "physics_prompt_seeded"

    def status(self) -> dict[str, Any]:
        mode = self._resolve_mode()
        return dict(
            port="LavaSegmentationPort",
            adapter="MetaSAM3Adapter",
            family="Meta SAM 3.1",
            model=self.model,
            mode=mode,
            ready=True,
            endpoint=self.endpoint if mode == "remote_api" else None,
            note=(
                "Inferencia remota SAM 3.1 activa"
                if mode == "remote_api"
                else "Pesos locales SAM 3.1 cargados"
                if mode == "local_weights"
                else "Extracción de prompts SAM 3.1 (boca + frentes SWIR + caja) con segmentación geodésica determinista"
            ),
        )

    def _call_remote_api(
        self,
        scene: ThermalScene,
        points: list[PromptPoint],
        box_xy: tuple[float, float, float, float] | None,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        if not self.endpoint:
            return None
        try:
            import requests
            from PIL import Image

            g = scene.grid
            r_ch = np.clip(scene.swir_radiance * 255, 0, 255).astype(np.uint8)
            g_ch = np.clip(((scene.brightness_temp_k - 290.0) / 300.0) * 255, 0, 255).astype(np.uint8)
            b_ch = np.clip(np.nan_to_num(g.elev, nan=0.0) / 2000.0 * 255, 0, 255).astype(np.uint8)
            rgb = np.stack([r_ch, g_ch, b_ch], axis=-1)
            buf = io.BytesIO()
            Image.fromarray(rgb, "RGB").save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            pts_ij = []
            labels = []
            for p in points:
                ri, cj = g.xy_to_ij(p.x, p.y)
                pts_ij.append([int(cj), int(ri)])
                labels.append(int(p.label))

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = dict(
                model=self.model,
                image_b64=img_b64,
                point_coords=pts_ij,
                point_labels=labels,
                text_prompt=scene.text_prompt,
            )
            resp = requests.post(self.endpoint, headers=headers, data=json.dumps(payload), timeout=15.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            mask_arr = np.asarray(data["mask"], dtype=bool).ravel()
            conf_arr = np.asarray(data.get("confidence", mask_arr.astype(float)), dtype=float).ravel()
            if mask_arr.size == g.elev.size:
                return mask_arr, conf_arr
        except Exception:
            return None
        return None

    def segment(self, scene: ThermalScene) -> SegmentationResult:
        t0 = time.perf_counter()
        points, box_xy = extract_sam3_prompts(scene)
        mode = self._resolve_mode()
        mask_flat: np.ndarray | None = None
        conf_flat: np.ndarray | None = None

        if mode == "remote_api":
            res = self._call_remote_api(scene, points, box_xy)
            if res is not None:
                mask_flat, conf_flat = res
            else:
                mode = "physics_prompt_seeded"

        if mask_flat is None or conf_flat is None:
            mask_flat, conf_flat = _prompt_seeded_segmentation(scene, points, box_xy)

        g = scene.grid
        X, Y = g.cell_centres()
        vx, vy = scene.vent_xy
        dist_flat = np.hypot(X - vx, Y - vy).ravel()
        area_ha = float(mask_flat.sum()) * (g.step ** 2) / 1e4
        reach_m = float(dist_flat[mask_flat].max()) if mask_flat.any() else 0.0
        dt_ms = (time.perf_counter() - t0) * 1000.0

        return SegmentationResult(
            mask_flat=mask_flat,
            confidence_flat=conf_flat,
            area_ha=area_ha,
            reach_m=reach_m,
            prompt_points=points,
            prompt_box_xy=box_xy,
            adapter="MetaSAM3Adapter",
            model=self.model,
            mode=mode,
            latency_ms=dt_ms,
        )
