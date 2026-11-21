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
    # NOAA's depth layer also paints open water; restrict both to land.
    sea_like = noaa_masks(0)[0]  # NOAA 0 ft (MHHW) inundation ~ existing water surface
    land = ~sea_like
    n_conn = noaa_conn & land
    r = dict(slr_ft=ft, noaa_connected_km2=round(n_conn.sum() * RES**2 / 1e6, 3),
             noaa_lowlying_disconnected_km2=round((noaa_low & land).sum() * RES**2 / 1e6, 3))
    for tag, path in (("used", PROC / f"flood_depth_{ft}ft.tif"), ("bathtub", HAZ / f"bathtub_{ft}ft.tif")):
        m = ours(path) & land
        inter, union = (n_conn & m).sum(), (n_conn | m).sum()
        r[f"{tag}_km2"] = round(m.sum() * RES**2 / 1e6, 3)
        r[f"{tag}_iou"] = round(inter / union, 3) if union else None
        r[f"{tag}_covers_noaa"] = round(inter / n_conn.sum(), 3) if n_conn.sum() else None
        if tag == "used":
            mine = m
    r = {k: (float(v) if isinstance(v, np.floating) else v) for k, v in r.items()}
    results.append(r)
    print(r)
    m = mine

    rgb = np.full((H, W, 3), 0.92)
    rgb[~land] = (0.75, 0.82, 0.92)
    rgb[n_conn & ~m] = (0.95, 0.55, 0.1)   # NOAA only
    rgb[m & ~n_conn] = (0.55, 0.2, 0.75)   # ours only
    rgb[m & n_conn] = (0.1, 0.35, 0.8)     # both
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(rgb)
    ax.set_title(f"+{ft} ft: blue = both, orange = NOAA only, purple = hazard we use only "
                 f"(IoU {r['used_iou']})", fontsize=13)
    ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(PROC / f"noaa_compare_{ft}ft.png", dpi=70, bbox_inches="tight")
    plt.close(fig)

expo = json.loads((PROC / "exposure_summary.json").read_text())
(PROC / "hazard_validation.json").write_text(json.dumps(
    dict(vs_noaa=results, art_vs_bathtub=expo["art_vs_bathtub"], art_bracket_for_5ft=expo["art_bracket"]), indent=2))
