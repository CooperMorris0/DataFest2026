"""Per-scenario flood hazard (ART primary, bathtub fallback) and exposure of buildings,
road segments, and critical facilities.

Hazard per scenario s (ft above MHHW, water level W_s = MHHW_NAVD88 + s):
  * ART level available: flooded = ART "inundated" extent (minus open bay / Lake Merritt).
    Depth is ESTIMATED as max(W_s - z, 0.01 m) from our 1 m LiDAR DEM inside ART's extent
    (ART's WMS does not expose its depth values). The 0.01 m floor keeps ART's extent intact
    where our DEM sits slightly above W_s; the share of such cells is reported.
    Low-lying = ART "disconnected low-lying" extent.
  * "5 ft" uses ART 66 in (5.5 ft; ART has no 60 in layer). Depth uses that map's level.
  * No ART level configured: bathtub model depth (flagged as fallback);
    low-lying = below W_s but not connected.
Exposure:
  * building: max depth over footprint, wet fraction, low-lying flag
  * road segment: max depth along it; impassable if > 0.15 m (bridges/tunnels excluded)
  * facility: flooded if its building footprint (or its own cell) floods; facilities outside
    the study area are kept (needed for routing) but marked in_study_area=False.
Outputs: data/processed/flood_depth_<ft>ft.tif, hazard/lowlying_<ft>ft.tif, flood_<ft>ft.png,
         buildings_exposure.geojson, roads_exposure.geojson, facilities_exposure.geojson,
         exposure_summary.json
"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from common import LineSampler, PolygonSampler, point_rowcol, read, write
from config import (ART_BRACKET_LEVELS_IN, ART_LEVEL_FOR_FT, CRS_METRIC, HAZ, IN_TO_M, MHHW_NAVD88_M, PROC, RAW,
                    ROAD_IMPASSABLE_DEPTH_M, SCENARIOS_FT, water_level_m)

z = read(HAZ / "dem_filled.tif")
sea = read(HAZ / "sea_mask.tif").astype(bool)
inland = read(HAZ / "inland_water.tif").astype(bool)
not_land = sea | inland

b = gpd.read_file(PROC / "buildings.geojson").to_crs(CRS_METRIC)
roads = gpd.read_file(RAW / "osm_roads.geojson").to_crs(CRS_METRIC)
roads["ekey"] = [tuple(sorted((u, v))) + (k,) for u, v, k in zip(roads.u, roads.v, roads.key)]
roads = roads.drop_duplicates("ekey").drop(columns="ekey").reset_index(drop=True)
fac = gpd.read_file(RAW / "facilities.geojson").to_crs(CRS_METRIC)

bs = PolygonSampler(list(b.geometry))
rs = LineSampler(list(roads.geometry))
print(f"buildings {len(b)} (fallback cells {bs.fallback}), road segments {len(roads)}, facilities {len(fac)}")
b["base_elev_m"] = bs.min(z).round(3)
roads["length_m"] = roads.length
roads["elevated_or_tunnel"] = roads["bridge"].fillna("no").ne("no") | roads["tunnel"].fillna("no").ne("no")

# facility -> containing building (if any) and its own cell
fr, fc, f_on = point_rowcol(fac.geometry.x, fac.geometry.y)
j = gpd.sjoin(fac[["geometry"]], b[["geometry"]], how="left", predicate="within")
j = j[~j.index.duplicated()]
fac["bldg_idx"] = j["index_right"].astype("Int64").values
fac["in_study_area"] = f_on


def hazard(ft):
    lvl = ART_LEVEL_FOR_FT.get(ft)
    # water level of the map actually used (ART 66 in for the "5 ft" scenario)
    W = MHHW_NAVD88_M + lvl * IN_TO_M if lvl is not None else water_level_m(ft)
    if lvl is not None:
        art = read(HAZ / f"art_{lvl}in.tif")
        ext = (art == 1) & ~not_land
        low = (art == 2) & ~not_land
        raw = W - z
        depth = np.where(ext, np.maximum(raw, 0.01), 0).astype(np.float32)
        info = dict(source="ART", art_level_in=lvl,
                    share_art_cells_dem_above_water=round(float((raw[ext] <= 0).mean()), 3) if ext.any() else None)
    else:
        depth = read(HAZ / f"bathtub_{ft}ft.tif")
        low = (z < W) & ~not_land & (depth == 0)
        info = dict(source="bathtub (fallback: no ART layer at this level)", art_level_in=None)
    return W, depth, low, info


def art_extent_only(lvl):
    art = read(HAZ / f"art_{lvl}in.tif")
    return ((art == 1) & ~not_land).astype(np.float32)


step = 3
summary = {"scenarios": [], "art_bracket": [], "art_vs_bathtub": []}
for ft in SCENARIOS_FT:
    sid = f"{ft}ft"
    W, depth, low, info = hazard(ft)
    write(PROC / f"flood_depth_{sid}.tif", depth)
    write(HAZ / f"lowlying_{sid}.tif", low.astype("uint8"))

    b[f"depth_{sid}"] = bs.max(depth).round(3)
    b[f"wet_frac_{sid}"] = bs.mean(depth > 0).round(3)
    b[f"lowlying_{sid}"] = bs.max(low.astype(np.float32)) > 0
    b[f"flooded_{sid}"] = b[f"depth_{sid}"] > 0
    roads[f"depth_{sid}"] = rs.max(depth).round(3)
    roads[f"impassable_{sid}"] = (roads[f"depth_{sid}"] > ROAD_IMPASSABLE_DEPTH_M) & ~roads["elevated_or_tunnel"]
    own = np.zeros(len(fac), bool)
    own[f_on] = depth[fr[f_on], fc[f_on]] > 0
    via_b = fac["bldg_idx"].map(lambda i: bool(b[f"flooded_{sid}"].iat[i]) if pd.notna(i) else False)
    fac[f"flooded_{sid}"] = own | via_b.values

    s = dict(id=sid, slr_ft=ft, water_level_navd88_m=round(W, 3), **info,
             flooded_land_km2=round(float((depth > 0).sum()) / 1e6, 4),
             lowlying_km2=round(float(low.sum()) / 1e6, 4),
             buildings_flooded=int(b[f"flooded_{sid}"].sum()),
             buildings_lowlying_only=int((b[f"lowlying_{sid}"] & ~b[f"flooded_{sid}"]).sum()),
             road_km_impassable=round(roads.loc[roads[f"impassable_{sid}"], "length_m"].sum() / 1000, 3),
             facilities_flooded=int(fac[f"flooded_{sid}"].sum()))
    summary["scenarios"].append(s)
    print(f"{sid}: {info['source'][:7]:7s} land {s['flooded_land_km2']:.3f} km2  bldg {s['buildings_flooded']:4d} "
          f"(+{s['buildings_lowlying_only']} low-lying)  road {s['road_km_impassable']:.2f} km  "
          f"facilities {s['facilities_flooded']}")

    # ART vs bathtub at the same water level (cross-check)
    if info["source"] == "ART" and ft > 0 and info["art_level_in"] == 12 * ft:  # same water level only
        bt = read(HAZ / f"bathtub_{sid}.tif") > 0
        a = depth > 0
        summary["art_vs_bathtub"].append(dict(
            slr_ft=ft, art_km2=round(a.sum() / 1e6, 3), bathtub_km2=round(bt.sum() / 1e6, 3),
            iou=round(float((a & bt).sum() / max(1, (a | bt).sum())), 3),
            art_buildings=s["buildings_flooded"], bathtub_buildings=int((bs.max(bt.astype(np.float32)) > 0).sum())))

    dd, ll = depth[::step, ::step], low[::step, ::step]
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(np.clip(z[::step, ::step], -1, 12), cmap="Greys_r", vmin=-1, vmax=12)
    ax.imshow(np.ma.masked_where(~sea[::step, ::step], sea[::step, ::step]), cmap=ListedColormap(["#9fb8d9"]), alpha=0.9)
    ax.imshow(np.ma.masked_where(~ll, ll), cmap=ListedColormap(["#2ca02c"]), alpha=0.6)
    im = ax.imshow(np.ma.masked_where(dd <= 0, dd), cmap="plasma_r", vmin=0, vmax=2)
    plt.colorbar(im, ax=ax, shrink=0.6, label="estimated depth (m)")
    ax.set_title(f"+{ft} ft ({info['source'].split(' ')[0]}{' ' + str(info['art_level_in']) + ' in' if info['art_level_in'] is not None else ''}): "
                 f"flooded (color), low-lying not connected (green)", fontsize=13)
    ax.set_xticks([]); ax.set_yticks([])
    fig.savefig(PROC / f"flood_{sid}.png", dpi=70, bbox_inches="tight")
    plt.close(fig)

for lvl in ART_BRACKET_LEVELS_IN:
    ext = art_extent_only(lvl)
    bf = bs.max(ext) > 0
    summary["art_bracket"].append(dict(art_level_in=lvl, slr_ft=round(lvl / 12, 2),
                                       flooded_land_km2=round(float(ext.sum()) / 1e6, 3),
                                       buildings_flooded=int(bf.sum())))
print("ART bracket for 5 ft:", summary["art_bracket"])
print("ART vs bathtub:", pd.DataFrame(summary["art_vs_bathtub"]).to_string(index=False))

# reference: buildings flooded by our bathtub model at each exact level (independent of ART)
summary["bathtub_buildings_by_ft"] = {
    str(ft): int((bs.max((read(HAZ / f"bathtub_{ft}ft.tif") > 0).astype(np.float32)) > 0).sum())
    for ft in SCENARIOS_FT}
print("bathtub buildings by ft:", summary["bathtub_buildings_by_ft"])
summary["n_buildings"] = len(b)
summary["n_road_segments"] = len(roads)
summary["road_km_total"] = round(roads["length_m"].sum() / 1000, 3)
summary["facilities_in_study_area"] = fac.loc[fac.in_study_area, "ftype"].value_counts().to_dict()
(PROC / "exposure_summary.json").write_text(json.dumps(summary, indent=2))
b.to_file(PROC / "buildings_exposure.geojson", driver="GeoJSON")
roads.to_file(PROC / "roads_exposure.geojson", driver="GeoJSON")
fac.drop(columns="bldg_idx").to_file(PROC / "facilities_exposure.geojson", driver="GeoJSON")
