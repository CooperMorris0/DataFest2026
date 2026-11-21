"""Validate the hazard layers against NOAA's Sea Level Rise Viewer (independent source).

Exports NOAA's connected-inundation layer for our exact grid from
coast.noaa.gov/arcgis/rest/services/dc_slr/slr_<N>ft/MapServer at 4 m and compares it with
(a) the hazard we use (ART for 1-4 ft, bathtub for 5 ft) and (b) our bathtub model,
on land only. ART-vs-bathtub agreement comes from 05 (exposure_summary.json).
Writes noaa_compare_<ft>ft.png and hazard_validation.json.
"""
import io
import json

import matplotlib
import numpy as np
import rasterio
import requests
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import GRID_BOUNDS, HAZ, PROC, RAW, SCENARIOS_FT, USER_AGENT

RES = 4  # m per pixel for the comparison
cache = RAW / "noaa_slr"
cache.mkdir(exist_ok=True)

class _B:  # grid bounds
    left, bottom, right, top = GRID_BOUNDS


b = _B
W = int((b.right - b.left) / RES)
H = int((b.top - b.bottom) / RES)


GREEN = np.array([85, 255, 0])  # NOAA's "low-lying (not connected)" symbol


def noaa_masks(ft):
    """Return (connected_depth, lowlying_disconnected) masks. The service draws both layers
    regardless of `layers=show:`, so classify by symbol color instead."""
    f = cache / f"slr_{ft}ft.png"
    if not f.exists():
        r = requests.get(
            f"https://coast.noaa.gov/arcgis/rest/services/dc_slr/slr_{ft}ft/MapServer/export",
            params=dict(bbox=f"{b.left},{b.bottom},{b.right},{b.top}", bboxSR=26910,
                        imageSR=26910, size=f"{W},{H}", layers="show:0,1",
                        format="png32", transparent="true", f="image"),
            headers={"User-Agent": USER_AGENT}, timeout=120)
        r.raise_for_status()
        assert r.headers.get("content-type", "").startswith("image"), r.text[:300]
        f.write_bytes(r.content)
    a = np.array(Image.open(f).convert("RGBA"))
    assert a.shape[:2] == (H, W), a.shape
    opaque = a[..., 3] > 0
    green = opaque & (np.abs(a[..., :3].astype(int) - GREEN).sum(-1) < 30)
    return opaque & ~green, green


def ours(path):
    with rasterio.open(path) as d:
        a = d.read(1)[: H * RES, : W * RES] > 0
    return a.reshape(H, RES, W, RES).any(axis=(1, 3))  # 4 m cell wet if any 1 m cell is


expo = json.loads((PROC / "exposure_summary.json").read_text())
used_level = {sc["slr_ft"]: (sc["art_level_in"] / 12 if sc["art_level_in"] is not None else sc["slr_ft"])
              for sc in expo["scenarios"]}
sea_like = noaa_masks('0')[0]  # NOAA 0 ft (MHHW) inundation ~ existing water surface
land = ~sea_like


def noaa_key(level_ft):
    return f"{int(level_ft)}" if float(level_ft).is_integer() else f"{int(level_ft)}_5"


def score(path, level_ft):
    """Compare a hazard raster with NOAA at the SAME water level (e.g. ART 66 in vs NOAA 5.5 ft)."""
    noaa_conn, noaa_low = noaa_masks(noaa_key(level_ft))
    if noaa_low.mean() > 0.95:
        # Observed 2026-11-21: NOAA's slr_3ft service renders every pixel as "low-lying"
        # for this area (any projection/size). Don't score it.
        return dict(noaa_level_ft=level_ft, noaa_unavailable="blank all-low-lying render"), None, None
    n_conn = noaa_conn & land
    m = ours(path) & land
    inter, union = (n_conn & m).sum(), (n_conn | m).sum()
    return dict(noaa_level_ft=level_ft, noaa_connected_km2=round(n_conn.sum() * RES**2 / 1e6, 3),
                km2=round(m.sum() * RES**2 / 1e6, 3), iou=round(float(inter / union), 3) if union else None,
                covers_noaa=round(float(inter / n_conn.sum()), 3) if n_conn.sum() else None), n_conn, m


results = []
for ft in [s for s in SCENARIOS_FT if s > 0]:
    used, n_conn, m = score(PROC / f"flood_depth_{ft}ft.tif", used_level[ft])
    bath, _, _ = score(HAZ / f"bathtub_{ft}ft.tif", ft)
    r = dict(scenario=f"{ft}ft", used=used, bathtub=bath)
    results.append(r)
    print(r)
    if m is None:
        continue
    rgb = np.full((H, W, 3), 0.92)
    rgb[~land] = (0.75, 0.82, 0.92)
    rgb[n_conn & ~m] = (0.95, 0.55, 0.1)   # NOAA only
    rgb[m & ~n_conn] = (0.55, 0.2, 0.75)   # ours only
    rgb[m & n_conn] = (0.1, 0.35, 0.8)     # both
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(rgb)
    ax.set_title(f"'{ft} ft' scenario vs NOAA {used_level[ft]:g} ft: blue = both, orange = NOAA only, "
                 f"purple = hazard we use only (IoU {used['iou']})", fontsize=12)
    ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(PROC / f"noaa_compare_{ft}ft.png", dpi=70, bbox_inches="tight")
    plt.close(fig)

(PROC / "hazard_validation.json").write_text(json.dumps(
    dict(vs_noaa=results, art_vs_bathtub=expo["art_vs_bathtub"], art_bracket_for_5ft=expo["art_bracket"]), indent=2))
