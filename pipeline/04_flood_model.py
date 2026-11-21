"""Connected 'bathtub' flood model.

  W_s = MHHW(NAVD88) + dSLR_s
  a cell floods if z < W_s AND it is 4-connected to open bay water (seeded flood fill).

4-connectivity (not 8) so water can't leak diagonally through 1-pixel seawalls.
Sea mask = OSM 'San Francisco Bay' polygon + estuary channel polygons, plus DEM nodata inside
them, restricted to components that contain a seed point well out in open water.

Outputs (data/processed/):
  sea_mask.png, flood_<ft>ft.png           visual checks
  flood_depth_<ft>ft.tif                    depth rasters (m), 0 where dry
  buildings_flood.geojson                   per-building base elev + depth per scenario
  roads_flood.geojson                       per-road-segment max depth + impassable flags
  flood_model_summary.json                  totals used by later steps
"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.fill import fillnodata
from scipy import ndimage
from shapely.geometry import Point, box
from shapely.ops import polygonize, unary_union

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

from config import (CRS_METRIC, DEM_NVA95_M, MHHW_NAVD88_M, PROC, RAW, ROAD_IMPASSABLE_DEPTH_M,
                    SCENARIOS, SEED_POINTS)

FOUR = ndimage.generate_binary_structure(2, 1)

# ---------------------------------------------------------------- DEM + sea mask
with rasterio.open(RAW / "dem_1m_navd88.tif") as d:
    z = d.read(1, masked=True)
    T, profile, shape = d.transform, d.profile, d.shape
nodata = z.mask.copy()
z = z.filled(np.nan).astype(np.float32)

water = gpd.read_file(RAW / "osm_water.geojson").to_crs(CRS_METRIC)
tf = Transformer.from_crs("EPSG:4326", CRS_METRIC, always_xy=True)
seed_pts = {n: Point(tf.transform(lon, lat)) for n, (lon, lat) in SEED_POINTS.items()}

# The OSM "San Francisco Bay" polygon is coarse (misses the harbors and estuary), but
# natural=coastline follows the real shore. Cut the DEM extent with the coastline and keep
# every piece that contains a seed. Union with the bay polygon and estuary-channel polygons.
frame = box(T.c, T.f + T.e * shape[0], T.c + T.a * shape[1], T.f)
coast = water[water["natural"] == "coastline"].geometry.intersection(frame)
pieces = list(polygonize(unary_union(list(coast) + [frame.boundary])))
sea_pieces = [p for p in pieces if any(p.contains(s) for s in seed_pts.values())]
print(f"coastline cut the frame into {len(pieces)} pieces; {len(sea_pieces)} contain seeds")
open_water_polys = water[((water["natural"] == "bay")
                          | water["name"].fillna("").str.contains("Estuar"))
                         & water.geom_type.isin(["Polygon", "MultiPolygon"])]
bay_poly = rasterize(((g, 1) for g in list(open_water_polys.geometry) + sea_pieces),
                     out_shape=shape, transform=T, fill=0, dtype="uint8").astype(bool)

# nodata inside the bay polygon is open water; give it a nominal bay floor depth.
# nodata on land (rare) is filled from neighbors.
z[nodata & bay_poly] = -2.0
land_holes = nodata & ~bay_poly
if land_holes.any():
    z = fillnodata(np.where(np.isnan(z), 0, z), mask=(~land_holes).astype("uint8"),
                   max_search_distance=50).astype(np.float32)
print(f"nodata: {nodata.mean():.3%} of cells ({(nodata & bay_poly).mean():.3%} in bay, "
      f"{land_holes.mean():.3%} on land, filled)")

seeds = {}
for name, pt in seed_pts.items():
    x, y = pt.x, pt.y
    r, c = rasterio.transform.rowcol(T, x, y)
    ok = 0 <= r < shape[0] and 0 <= c < shape[1] and bay_poly[r, c] and z[r, c] < MHHW_NAVD88_M
    print(f"seed {name:28s} row {r:5d} col {c:5d} z={z[r, c]:6.2f} in_bay={bool(bay_poly[r, c])}")
    assert ok, f"seed {name} is not in open water"
    seeds[name] = (r, c)

# Permanent inland water (Lake Merritt lagoon + its channel): can convey water, but is not
# counted as flooded land. (Real-world Lake Merritt is tide-gated; not modeled.)
inland = water[water["water"].isin(["lagoon", "river"]) & water.geom_type.isin(["Polygon", "MultiPolygon"])]
inland_water = rasterize(((g, 1) for g in inland.geometry), out_shape=shape, transform=T,
                         fill=0, dtype="uint8").astype(bool) & ~bay_poly
print(f"inland water excluded from land totals: {inland_water.sum() / 1e6:.3f} km2 "
      f"({', '.join(inland['name'].dropna().unique())})")

lab, _ = ndimage.label(bay_poly, structure=FOUR)
seed_labels = {lab[r, c] for r, c in seeds.values()}
sea = np.isin(lab, list(seed_labels))
print(f"sea mask: {sea.mean():.1%} of bbox; components seeded: {len(seed_labels)}")


# ---------------------------------------------------------------- per-feature samplers
b = gpd.read_file(PROC / "buildings.geojson")
ids = rasterize(((g, int(i) + 1) for g, i in zip(b.geometry, b["bid"])), out_shape=shape,
                transform=T, fill=0, dtype="int32")
# tiny footprints that capture no cell center fall back to their representative-point cell
present = np.zeros(len(b) + 1, bool)
present[np.unique(ids)] = True
missing = np.where(~present[1:])[0]
for i in missing:
    pt = b.geometry.iat[i].representative_point()
    r, c = rasterio.transform.rowcol(T, pt.x, pt.y)
    if ids[r, c] == 0:
        ids[r, c] = i + 1
print(f"buildings with centroid fallback: {len(missing)}")
bidx = np.arange(1, len(b) + 1)
b["base_elev_m"] = ndimage.minimum(z, ids, bidx).round(3)

roads = gpd.read_file(RAW / "osm_roads.geojson").to_crs(CRS_METRIC)
# osmnx stores two-way streets twice (u->v and v->u); keep one per undirected edge
roads["ekey"] = [tuple(sorted((u, v))) + (k,) for u, v, k in zip(roads.u, roads.v, roads.key)]
roads = roads.drop_duplicates("ekey").drop(columns="ekey").reset_index(drop=True)
H, Wd = shape
inv = ~T
rr_, cc_, starts = [], [], []
for g in roads.geometry:  # sample every ~1 m along each segment, once
    n = max(2, int(g.length))
    pts = [g.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
    cols, rows = zip(*[inv * (p.x, p.y) for p in pts])
    starts.append(len(rr_))
    rr_.extend(np.clip(np.array(rows, int), 0, H - 1))
    cc_.extend(np.clip(np.array(cols, int), 0, Wd - 1))
rr_, cc_, starts = np.array(rr_), np.array(cc_), np.array(starts)
roads["min_ground_m"] = np.round(np.minimum.reduceat(z[rr_, cc_], starts), 3)
elevated = roads["bridge"].fillna("no").ne("no") | roads["tunnel"].fillna("no").ne("no")
roads["elevated_or_tunnel"] = elevated
roads["length_m"] = roads.length

# ---------------------------------------------------------------- PNG helpers
step = 3
ex = [T.c, T.c + T.a * shape[1], T.f + T.e * shape[0], T.f]
seed_xy = [rasterio.transform.xy(T, r, c) for r, c in seeds.values()]
sea_s = sea[::step, ::step]


def base_plot(title):
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(np.clip(z[::step, ::step], -1, 12), extent=ex, cmap="Greys_r", vmin=-1, vmax=12)
    ax.set_title(title, fontsize=14)
    ax.set_xticks([]); ax.set_yticks([])
    return fig, ax


fig, ax = base_plot("Sea mask (seeded open water) - stars are flood-fill seeds")
ax.imshow(np.ma.masked_where(~sea_s, sea_s), extent=ex, cmap=ListedColormap(["#1f5fbf"]), alpha=0.75)
ax.plot(*zip(*seed_xy), "y*", ms=18, mec="k")
fig.savefig(PROC / "sea_mask.png", dpi=70, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------- flood fill
def flood(W):
    """Connected flooding at water level W. Returns (land depth raster, disconnected-low mask)."""
    wet = sea | (z < W)
    lab, _ = ndimage.label(wet, structure=FOUR)
    keep = np.unique([lab[r, c] for r, c in seeds.values()])
    conn = np.isin(lab, keep[keep > 0])
    land_flood = conn & ~sea & ~inland_water
    return np.where(land_flood, W - z, 0).astype(np.float32), wet & ~conn & ~inland_water


cell_km2 = abs(T.a * T.e) / 1e6
summary = {"mhhw_navd88_m": MHHW_NAVD88_M, "dem_nva95_m": DEM_NVA95_M, "scenarios": []}
for sc in SCENARIOS:
    sid, W = sc["id"], sc["water_m"]
    depth, disc = flood(W)
    b[f"depth_{sid}"] = ndimage.maximum(depth, ids, bidx).round(3)
    b[f"wet_frac_{sid}"] = ndimage.mean(depth > 0, ids, bidx).round(3)
    roads[f"depth_{sid}"] = np.round(np.maximum.reduceat(depth[rr_, cc_], starts), 3)
    # bridges/viaducts sit above the bare-earth DEM, so they are never impassable here
    roads[f"impassable_{sid}"] = (roads[f"depth_{sid}"] > ROAD_IMPASSABLE_DEPTH_M) & ~elevated
    s = dict(id=sid, slr_ft=sc["slr_ft"], storm=sc["storm"], water_level_navd88_m=round(W, 4),
             flooded_land_km2=round((depth > 0).sum() * cell_km2, 4),
             disconnected_low_km2=round(disc.sum() * cell_km2, 4),
             buildings_flooded=int((b[f"depth_{sid}"] > 0).sum()),
             road_km_impassable=round(roads.loc[roads[f"impassable_{sid}"], "length_m"].sum() / 1000, 3),
             road_segments_impassable=int(roads[f"impassable_{sid}"].sum()))

    p = profile.copy()
    p.update(dtype="float32", nodata=0, compress="deflate", predictor=3)
    with rasterio.open(PROC / f"flood_depth_{sid}.tif", "w", **p) as dst:
        dst.write(depth, 1)
    dd = depth[::step, ::step]
    label = f"+{sc['slr_ft']} ft SLR" + (" + 100-yr storm tide" if sc["storm"] else "")
    fig, ax = base_plot(f"{label} (water {W:.2f} m NAVD88): connected flooding, depth m")
    ax.imshow(np.ma.masked_where(~sea_s, sea_s), extent=ex, cmap=ListedColormap(["#9fb8d9"]), alpha=0.9)
    im = ax.imshow(np.ma.masked_where(dd <= 0, dd), extent=ex, cmap="plasma_r", vmin=0, vmax=2)
    plt.colorbar(im, ax=ax, shrink=0.6, label="depth (m)")
    fig.savefig(PROC / f"flood_{sid}.png", dpi=70, bbox_inches="tight")
    plt.close(fig)
    del depth, disc

    # DEM vertical-accuracy envelope: rerun with water +/- NVA95 (a uniform DEM bias bound)
    for tag, dW in (("lo", -DEM_NVA95_M), ("hi", DEM_NVA95_M)):
        d2, _ = flood(W + dW)
        b[f"flooded_{sid}_{tag}"] = ndimage.maximum(d2, ids, bidx) > 0
        imp = (np.maximum.reduceat(d2[rr_, cc_], starts) > ROAD_IMPASSABLE_DEPTH_M) & ~elevated
        s[f"buildings_flooded_{tag}"] = int(b[f"flooded_{sid}_{tag}"].sum())
        s[f"road_km_impassable_{tag}"] = round(roads.loc[imp, "length_m"].sum() / 1000, 3)
        del d2
    summary["scenarios"].append(s)
    print(f"{sid:10s} W={W:.3f}  land {s['flooded_land_km2']:6.3f} km2  bldg {s['buildings_flooded']:5d} "
          f"[{s['buildings_flooded_lo']}-{s['buildings_flooded_hi']}]  road {s['road_km_impassable']:6.2f} km")

b.to_file(PROC / "buildings_flood.geojson", driver="GeoJSON")
roads.to_file(PROC / "roads_flood.geojson", driver="GeoJSON")
summary["n_buildings"] = len(b)
summary["road_km_total"] = round(roads["length_m"].sum() / 1000, 3)
summary["n_road_segments"] = len(roads)
(PROC / "flood_model_summary.json").write_text(json.dumps(summary, indent=2))
print(f"buildings {len(b)}, road segments {len(roads)}, road km {summary['road_km_total']}")
