"""Bring Kai's FloodWatch website (rain / storm-drain flooding TODAY) into the Roblox viewer,
so the website's hex map and the 3D world line up exactly.

Owned by the viewer side (Cooper). It only READS FloodWatch outputs, never edits them.
Sources (first that exists):
  1. data/processed/floodwatch/hexes_roblox.json   <- K2 deliverable from Kai's agents
  2. oakland-flood-vulnerability/outputs/hex_scores.csv + .geojson (FloodWatch)
Optional: data/processed/floodwatch/hex_slr.csv (K1, sea-level-rise share per hex).

Congruence with the website (oakland-flood-vulnerability/map_template.html):
  * same H3 res-9 hexes, outlines from the SAME geojson geometry (EPSG:4326 -> EPSG:26910 ->
    our local frame), so a hex edge crosses the same street in both;
  * same risk categories + colors. If the CSV has `risk` / `fvi_pct` (website build), they
    are used as-is; otherwise they're recomputed with the website's rule:
    fvi_pct = citywide percentile rank of fvi (0-1); >=0.9 Very high, >=0.7 High,
    >=0.4 Moderate, >=0.2 Low, else Very low (shown rounded to a whole percent).
  * same panel fields (risk, fvi_pct, hazard_pct, svi, p_flood, flood_reports, FEMA, why...).

Output: data/processed/roblox/floodwatch.json
  hexes: [{id, h3, risk, fvi_pct, hazard_pct, svi, p_flood, reports, drains, fema, elev_ft,
           under, no_car, why, tract, cx, cz, r, rot, poly, slr}]   (meters, local frame)
  edges: [[ [x, z, elev_m], ... ], ...]  unique hex edges sampled every ~25 m on our DEM
  bldg_hex: [[bid, hex_id], ...]
"""
import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from common import GRID_TRANSFORM, read
from config import CRS_METRIC, GRID_BOUNDS, HAZ, PROC, ROOT

X0, Y0 = GRID_BOUNDS[0], GRID_BOUNDS[1]
FW = ROOT / "oakland-flood-vulnerability" / "outputs"
K2 = PROC / "floodwatch" / "hexes_roblox.json"
K1 = PROC / "floodwatch" / "hex_slr.csv"
OUT = PROC / "roblox" / "floodwatch.json"
CATS = [(0.9, "Very high"), (0.7, "High"), (0.4, "Moderate"), (0.2, "Low"), (0.0, "Very low")]  # website rule
EDGE_STEP_M = 25

if K2.exists():
    src = "K2 hexes_roblox.json"
    attrs = pd.DataFrame(json.loads(K2.read_text()))
else:
    src = "FloodWatch outputs/hex_scores.csv"
    attrs = pd.read_csv(FW / "hex_scores.csv")

# percentiles are CITYWIDE (all Oakland hexes), exactly like the website
# fvi_pct is a 0-1 fraction on the website build; categories use the UNROUNDED value
if "fvi_pct" not in attrs:
    attrs["fvi_pct"] = attrs["fvi"].rank(pct=True)
    src += " (risk/fvi_pct recomputed with the website rule)"
elif attrs["fvi_pct"].max() > 1.5:   # tolerate a 0-100 version
    attrs["fvi_pct"] = attrs["fvi_pct"] / 100
if "risk" not in attrs:
    attrs["risk"] = attrs["fvi_pct"].apply(lambda p: next(c for t, c in CATS if p >= t))
attrs["hazard_pct"] = attrs["hazard"].rank(pct=True) if "hazard" in attrs else 0.0

geo = gpd.read_file(FW / "hex_scores.geojson")[["h3", "geometry"]].to_crs(CRS_METRIC)
hexes = geo.merge(attrs, on="h3", how="left")
frame = box(*GRID_BOUNDS)
hexes = hexes[hexes.intersects(frame)].reset_index(drop=True)
hexes["id"] = np.arange(1, len(hexes) + 1)


def g(r, k, d=0):
    v = r.get(k, d)
    return d if v is None or (isinstance(v, float) and math.isnan(v)) else v


def fema(r):
    if g(r, "in_sfha", 0):
        return "In FEMA 100-year flood zone"
    if g(r, "in_500yr", 0):
        return "In FEMA 500-year flood zone"
    return "Outside FEMA flood zones"


slr = {}
if K1.exists():
    k1 = pd.read_csv(K1)
    if "flooded_share" in k1:
        for h, grp in k1.groupby("h3"):
            slr[h] = {str(r.scenario): round(float(r.flooded_share), 3) for _, r in grp.iterrows()}

z = read(HAZ / "dem_filled.tif")
inv = ~GRID_TRANSFORM


def elev(x, y):
    c, r = inv * (x, y)
    r = min(max(int(r), 0), z.shape[0] - 1)
    c = min(max(int(c), 0), z.shape[1] - 1)
    return round(float(z[r, c]), 2)


def loc(x, y):
    return [round(x - X0, 1), round(-(y - Y0), 1)]


recs, edge_set = [], {}
for _, r in hexes.iterrows():
    ring = list(r.geometry.exterior.coords)[:-1]
    c = r.geometry.centroid
    rad = float(np.mean([math.hypot(x - c.x, y - c.y) for x, y in ring]))
    rot = math.degrees(math.atan2(ring[0][1] - c.y, ring[0][0] - c.x))
    recs.append(dict(
        id=int(r.id), h3=r.h3, risk=g(r, "risk", "Very low"), fvi_pct=int(round(100 * float(g(r, "fvi_pct", 0)))),
        hazard_pct=int(round(100 * float(g(r, "hazard_pct", 0)))), svi=round(float(g(r, "vulnerability", g(r, "svi_overall", 0))), 3),
        p_flood=int(round(float(g(r, "p_flood", 0)) * (100 if float(g(r, "p_flood", 0)) <= 1 else 1))),
        reports=int(g(r, "flood_reports", 0)), drains=int(g(r, "drain_reports", 0)), fema=fema(r),
        elev_ft=round(float(g(r, "elev_ft", 0)), 1), under=bool(g(r, "maybe_underreported", False)),
        no_car=round(float(g(r, "pct_no_vehicle", 0)), 1), why=str(g(r, "why", "") or ""),
        tract=str(g(r, "GEOID", ""))[-6:], cx=loc(c.x, c.y)[0], cz=loc(c.x, c.y)[1],
        r=round(rad, 1), rot=round(rot, 1), poly=[loc(x, y) for x, y in ring], slr=slr.get(r.h3, {})))
    # unique edges (shared by two hexes) keyed on rounded endpoints
    for a, b in zip(ring, ring[1:] + ring[:1]):
        key = tuple(sorted([(round(a[0], 1), round(a[1], 1)), (round(b[0], 1), round(b[1], 1))]))
        if key not in edge_set:
            n = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) // EDGE_STEP_M))
            pts = []
            for t in np.linspace(0, 1, n + 1):
                x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if frame.contains(box(x, y, x, y).centroid):
                    pts.append(loc(x, y) + [elev(x, y)])
            if len(pts) >= 2:
                edge_set[key] = pts

b = gpd.read_file(PROC / "buildings_final.geojson")[["bid", "geometry"]].to_crs(CRS_METRIC)
pts = gpd.GeoDataFrame(b[["bid"]], geometry=b.geometry.representative_point(), crs=CRS_METRIC)
j = gpd.sjoin(pts, hexes[["id", "geometry"]], how="left", predicate="within")
j = j[~j.index.duplicated()]
bldg_hex = [[int(bid), int(h)] for bid, h in zip(j["bid"], j["id"]) if pd.notna(h)]

out = dict(source=src, k1_slr_included=bool(slr), n_hexes=len(recs),
           reports_total=int(sum(r["reports"] for r in recs)),
           risk_counts={c: sum(r["risk"] == c for r in recs) for _, c in CATS},
           hexes=recs, edges=list(edge_set.values()), bldg_hex=bldg_hex,
           note="311 storm-drain flood reports 2013-2026 and FloodWatch risk index (Kai). "
                "Reports partly reflect who calls 311; see FloodWatch README.")
OUT.write_text(json.dumps(out, separators=(",", ":"), allow_nan=False))
nseg = sum(len(e) - 1 for e in edge_set.values())
print(f"FloodWatch -> viewer: {len(recs)} hexes ({src}); {out['reports_total']} 311 reports; "
      f"risk {out['risk_counts']}; {len(edge_set)} edges / {nseg} outline segments; "
      f"{len(bldg_hex)}/{len(b)} buildings matched; K1 SLR: {bool(slr)}")
