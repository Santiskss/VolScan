"""Textures for the 3D atlas: relief shaded with the editorial palette, and the lava overlay in grid space."""
from __future__ import annotations

import base64
import io

import numpy as np

# Editorial palette (shared language with the PyroScan atlas: sand, ochre, sea in neutral grey)
SEA = np.array([214, 219, 221])
LOW = np.array([226, 209, 176])
MID = np.array([204, 176, 133])
HIGH = np.array([163, 134, 98])
PEAK = np.array([120, 98, 76])


def upsample(z: np.ndarray, k: int) -> np.ndarray:
    """Bilinear upsampling by an integer factor k. NaN (sea) is propagated without inventing land."""
    rows, cols = z.shape
    yi = (np.arange(rows * k) + 0.5) / k - 0.5
    xi = (np.arange(cols * k) + 0.5) / k - 0.5
    y0 = np.clip(np.floor(yi).astype(int), 0, rows - 2)
    x0 = np.clip(np.floor(xi).astype(int), 0, cols - 2)
    fy = np.clip(yi - y0, 0, 1)[:, None]
    fx = np.clip(xi - x0, 0, 1)[None, :]
    a = z[y0][:, x0]
    b = z[y0][:, x0 + 1]
    c = z[y0 + 1][:, x0]
    d = z[y0 + 1][:, x0 + 1]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def hillshade(z: np.ndarray, step: float, azimuth=315.0, altitude=40.0, exaggeration=1.5) -> np.ndarray:
    zz = np.where(np.isnan(z), 0.0, z) * exaggeration
    gy, gx = np.gradient(zz, step)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    az, alt = np.radians(azimuth), np.radians(altitude)
    hs = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1)


def relief_rgb(z: np.ndarray, step: float) -> np.ndarray:
    land = ~np.isnan(z)
    zmax = np.nanmax(z) if land.any() else 1.0
    t = np.clip(np.where(land, z, 0) / max(zmax, 1.0), 0, 1)[..., None]
    stops = [(0.0, LOW), (0.35, MID), (0.75, HIGH), (1.0, PEAK)]
    col = np.zeros(z.shape + (3,))
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= t0) & (t <= t1)
        f = (t - t0) / (t1 - t0)
        col = np.where(m, c0 + (c1 - c0) * f, col)
    hs = hillshade(z, step)[..., None]
    shade = 0.55 + 0.6 * hs
    rgb = np.clip(col * shade, 0, 255)
    rgb = np.where(land[..., None], rgb, SEA)
    return rgb.astype(np.uint8)


def png_data_url(arr: np.ndarray, mode: str) -> str:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr, mode).save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def lava_overlay_rgba(prob: np.ndarray, observed: np.ndarray | None) -> np.ndarray:
    """Probability in warm tones plus the outline of the observed flow (dark ink, like the CEMS atlas)."""
    p = np.clip(prob, 0, 1)
    r = 150 + 105 * np.sqrt(p)
    g = 40 + 170 * p ** 1.6
    b = 20 + 30 * p ** 3
    a = np.where(p > 0.01, 70 + 170 * np.sqrt(p), 0)
    rgba = np.stack([r, g, b, a], -1)
    if observed is not None:
        m = observed.astype(bool)
        fill = m & (p <= 0.01)
        rgba[fill] = [70, 46, 36, 150]
        edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
        rgba[edge] = [40, 26, 20, 255]
    return np.clip(rgba, 0, 255).astype(np.uint8)


def heights_b64(z: np.ndarray) -> str:
    """Int16 metres (little-endian), nodata = -32768, base64."""
    zi = np.where(np.isnan(z), -32768, np.round(z)).astype("<i2")
    return base64.b64encode(zi.tobytes()).decode()
