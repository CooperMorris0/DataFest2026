"""Connected 'bathtub' flood model on the 1 m LiDAR DEM: FALLBACK hazard + shared masks.

Used for (a) scenarios ART doesn't publish (5 ft = 60 in), (b) cross-checking ART, and
(c) supplementary 100-year storm-tide and DEM-uncertainty runs.

  W_s = MHHW(NAVD88) + dSLR_s ;  a cell floods if z < W_s AND it is 4-connected to the bay.

4-connectivity (not 8) so water can't leak diagonally through 1-pixel seawalls.
Sea mask = the DEM extent cut along OSM natural=coastline, keeping pieces that contain
seed points in open water (+ OSM bay/estuary polygons). Lake Merritt + channel are inland
water: they convey flooding but aren't counted as flooded land.

Outputs (data/processed/hazard/):
  dem_filled.tif, sea_mask.tif, inland_water.tif   shared by later steps
  bathtub_<id>.tif                                 depth (m), 0 where dry; id = <ft>ft,
                                                   <ft>ft_lo / _hi (water -/+ DEM NVA95),
                                                   <ft>ft_100yr (+ 100-yr storm tide)
  bathtub_summary.json ; ../sea_mask.png ; ../bathtub_<ft>ft.png
"""
import json

import geopandas as gpd
import matplotlib
import numpy as np
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

from common import GRID_SHAPE, GRID_TRANSFORM, write
from config import (CRS_METRIC, DEM_NVA95_M, FT_TO_M, HAZ, MHHW_NAVD88_M, PROC, RAW,
                    SCENARIOS_FT, SEED_POINTS, SURGE_100YR_M, water_level_m)

FOUR = ndimage.generate_binary_structure(2, 1)

# ---------------------------------------------------------------- DEM + sea mask
with rasterio.open(RAW / "dem_1m_navd88.tif") as d:
    assert d.shape == GRID_SHAPE and d.transform.almost_equals(GRID_TRANSFORM)
    z = d.read(1, masked=True)
    T, shape = d.transform, d.shape
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

write(HAZ / "dem_filled.tif", z.astype("float32"))
write(HAZ / "sea_mask.tif", sea.astype("uint8"))
write(HAZ / "inland_water.tif", inland_water.astype("uint8"))


def flood(W):
    """Connected flooding at water level W -> (land depth raster, disconnected-low mask)."""
    wet = sea | (z < W)
    lab, _ = ndimage.label(wet, structure=FOUR)
    keep = np.unique([lab[r, c] for r, c in seeds.values()])
    conn = np.isin(lab, keep[keep > 0])
    land = conn & ~sea & ~inland_water
    return np.where(land, W - z, 0).astype(np.float32), wet & ~conn & ~inland_water


runs = []
for ft in SCENARIOS_FT:
    W = water_level_m(ft)
    runs += [(f"{ft}ft", ft, W), (f"{ft}ft_lo", ft, W - DEM_NVA95_M), (f"{ft}ft_hi", ft, W + DEM_NVA95_M),
             (f"{ft}ft_100yr", ft, W + SURGE_100YR_M)]

step = 3
sea_s = sea[::step, ::step]


def base_plot(title):
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.imshow(np.clip(z[::step, ::step], -1, 12), cmap="Greys_r", vmin=-1, vmax=12)
    ax.set_title(title, fontsize=14)
    ax.set_xticks([]); ax.set_yticks([])
    return fig, ax


fig, ax = base_plot("Sea mask (seeded open water) - stars are flood-fill seeds")
ax.imshow(np.ma.masked_where(~sea_s, sea_s), cmap=ListedColormap(["#1f5fbf"]), alpha=0.75)
for r, c in seeds.values():
    ax.plot(c / step, r / step, "y*", ms=18, mec="k")
fig.savefig(PROC / "sea_mask.png", dpi=70, bbox_inches="tight")
plt.close(fig)

summary = {"mhhw_navd88_m": MHHW_NAVD88_M, "dem_nva95_m": DEM_NVA95_M,
           "surge_100yr_m": SURGE_100YR_M, "runs": []}
for rid, ft, W in runs:
    depth, disc = flood(W)
    write(HAZ / f"bathtub_{rid}.tif", depth)
    summary["runs"].append(dict(id=rid, slr_ft=ft, water_level_navd88_m=round(W, 4),
                                flooded_land_km2=round((depth > 0).sum() / 1e6, 4),
                                disconnected_low_km2=round(disc.sum() / 1e6, 4)))
    print(f"bathtub {rid:10s} W={W:.3f}  flooded land {(depth > 0).sum() / 1e6:6.3f} km2  "
          f"disconnected low {disc.sum() / 1e6:6.3f} km2")
    if rid == f"{ft}ft":
        dd = depth[::step, ::step]
        fig, ax = base_plot(f"Bathtub +{ft} ft (water {W:.2f} m NAVD88): connected flooding, depth m")
        ax.imshow(np.ma.masked_where(~sea_s, sea_s), cmap=ListedColormap(["#9fb8d9"]), alpha=0.9)
        im = ax.imshow(np.ma.masked_where(dd <= 0, dd), cmap="plasma_r", vmin=0, vmax=2)
        plt.colorbar(im, ax=ax, shrink=0.6, label="depth (m)")
        fig.savefig(PROC / f"bathtub_{ft}ft.png", dpi=70, bbox_inches="tight")
        plt.close(fig)
(HAZ / "bathtub_summary.json").write_text(json.dumps(summary, indent=2))
