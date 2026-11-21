"""Validate our connected-bathtub extents against NOAA's Sea Level Rise Viewer.

Exports NOAA's 'SLR Depth' layer (connected inundation) for our exact bbox from
coast.noaa.gov/arcgis/rest/services/dc_slr/slr_<N>ft/MapServer at 4 m, then compares it
with our flooded-land mask (sea and inland water excluded from both).
Writes noaa_compare_<ft>ft.png and noaa_validation.json.
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

from config import PROC, RAW, SCENARIOS_FT, USER_AGENT

RES = 4  # m per pixel for the comparison
cache = RAW / "noaa_slr"
cache.mkdir(exist_ok=True)

with rasterio.open(PROC / "flood_depth_0ft.tif") as d:
    b = d.bounds
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


def ours(ft):
    with rasterio.open(PROC / f"flood_depth_{ft}ft.tif") as d:
        a = d.read(1)[: H * RES, : W * RES] > 0
    return a.reshape(H, RES, W, RES).any(axis=(1, 3))  # 4 m cell wet if any 1 m cell is


# Land = not sea / inland water in our model. Use NOAA 0 ft depth too as a sanity reference.
results = []
for ft in [s for s in SCENARIOS_FT if s > 0]:
    noaa_conn, noaa_low = noaa_masks(ft)
    if noaa_low.mean() > 0.95:
        # Observed 2026-11-21: NOAA's slr_3ft service renders every pixel as "low-lying"
        # for this area (any projection/size); slr_4ft renders correctly. Don't score it.
        r = dict(slr_ft=ft, noaa_unavailable="NOAA service returned a blank all-low-lying render")
        results.append(r)
        print(r)
        continue
    mine = ours(ft)
    # NOAA's depth layer also paints open water; restrict both to land.
    sea_like = noaa_masks(0)[0]  # NOAA 0 ft (MHHW) inundation ~ existing water surface
    land = ~sea_like
    n_conn, m = noaa_conn & land, mine & land
    inter, union = (n_conn & m).sum(), (n_conn | m).sum()
    r = dict(slr_ft=ft,
             noaa_connected_km2=round(n_conn.sum() * RES**2 / 1e6, 3),
             noaa_lowlying_disconnected_km2=round((noaa_low & land).sum() * RES**2 / 1e6, 3),
             ours_km2=round(m.sum() * RES**2 / 1e6, 3),
             iou=round(inter / union, 3) if union else None,
             ours_covered_by_noaa=round(inter / m.sum(), 3) if m.sum() else None,
             noaa_covered_by_ours=round(inter / n_conn.sum(), 3) if n_conn.sum() else None)
    r = {k: (float(v) if isinstance(v, np.floating) else v) for k, v in r.items()}
    results.append(r)
    print(r)

    rgb = np.full((H, W, 3), 0.92)
    rgb[~land] = (0.75, 0.82, 0.92)
    rgb[n_conn & ~m] = (0.95, 0.55, 0.1)   # NOAA only
    rgb[m & ~n_conn] = (0.55, 0.2, 0.75)   # ours only
    rgb[m & n_conn] = (0.1, 0.35, 0.8)     # both
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(rgb)
    ax.set_title(f"+{ft} ft: blue = both, orange = NOAA only, purple = ours only "
                 f"(IoU {r['iou']})", fontsize=13)
    ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(PROC / f"noaa_compare_{ft}ft.png", dpi=70, bbox_inches="tight")
    plt.close(fig)

(PROC / "noaa_validation.json").write_text(json.dumps(results, indent=2))
