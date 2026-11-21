"""World geometry for the Roblox viewer: terrain tiles + water surface rectangles.

Frame (same as 08): local meters = EPSG:26910 minus the grid's SW corner; Roblox X = east,
Z = -north, Y = up; 1 stud = 0.28 m. Terrain cell (i, k) = one 4-stud voxel column
(1.12 m), i from the west edge, k from the SOUTH edge, covering
X in [4i, 4i+4] and Z in [-4(k+1), -4k] studs.

data/processed/roblox/terrain/tile_<ti>_<tk>.bin  (128 x 128 columns per tile)
    little-endian: u16 cols, u16 rows, then cols*rows u16 heights (row-major, k then i),
    then cols*rows u8 materials.   height_m = ZMIN + v / 65535 * (ZMAX - ZMIN)
    materials: 0 Pavement, 1 Asphalt, 2 Grass, 3 Mud, 4 Rock
data/processed/roblox/water.json
    sea / inland / per-scenario flood rectangles on a 32-stud (8.96 m) grid, in studs:
    [x0, z0, x1, z1] (x0<x1, z0<z1). Flood rects use "any flooded 1 m cell" so they may
    overshoot dry ground slightly; the terrain above the water plane hides that.
"""
import json
import math

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject

from common import GRID_SHAPE, GRID_TRANSFORM, read
from config import CRS_METRIC, GRID_BOUNDS, HAZ, PROC, RAW, SCENARIO_IDS, STUDS_PER_METER

OUT = PROC / "roblox"
TER = OUT / "terrain"
TER.mkdir(parents=True, exist_ok=True)
for f in TER.glob("*.bin"):
    f.unlink()

VOX_STUDS = 4
CELL_M = VOX_STUDS / STUDS_PER_METER          # 1.12 m
TILE = 128
ZMIN, ZMAX = -12.0, 42.0
L, B, R, T = GRID_BOUNDS
NI = int((R - L) // CELL_M)                    # columns (west -> east)
NK = int((T - B) // CELL_M)                    # rows (south -> north)
# north-up raster on this grid, top edge at B + NK*CELL_M
vt = from_origin(L, B + NK * CELL_M, CELL_M, CELL_M)

# ------------------------------------------------------------ heights (block average)
dem = read(HAZ / "dem_filled.tif").astype(np.float32)
h = np.empty((NK, NI), np.float32)
reproject(dem, h, src_transform=GRID_TRANSFORM, src_crs=CRS_METRIC, dst_transform=vt,
          dst_crs=CRS_METRIC, resampling=Resampling.average)
h = np.clip(h, ZMIN, ZMAX)


def to_vox(a, resampling=Resampling.max):
    out = np.zeros((NK, NI), np.float32)
    reproject(a.astype(np.float32), out, src_transform=GRID_TRANSFORM, src_crs=CRS_METRIC,
              dst_transform=vt, dst_crs=CRS_METRIC, resampling=resampling)
    return out


# ------------------------------------------------------------ materials
sea = to_vox(read(HAZ / "sea_mask.tif"), Resampling.average) > 0.5
inland = to_vox(read(HAZ / "inland_water.tif"), Resampling.average) > 0.5
roads = gpd.read_file(PROC / "roads_final.geojson").to_crs(CRS_METRIC)
widths = {"motorway": 14, "trunk": 12, "primary": 12, "secondary": 10, "tertiary": 9,
          "residential": 8, "unclassified": 7, "service": 5, "living_street": 5}
roads["w"] = roads["highway"].astype(str).str.split(";").str[0].str.replace("_link", "").map(widths).fillna(7)
road_mask = rasterize(((g.buffer(w / 2), 1) for g, w in zip(roads.geometry, roads["w"])),
                      out_shape=(NK, NI), transform=vt, fill=0, dtype="uint8").astype(bool)
lu = gpd.read_file(RAW / "landuse_parcels.geojson").to_crs(CRS_METRIC)
parks = lu[lu["mtc_land_use_category"].isin(["Open Space"])]
park_mask = rasterize(((g, 1) for g in parks.geometry), out_shape=(NK, NI), transform=vt,
                      fill=0, dtype="uint8").astype(bool)
gy, gx = np.gradient(h, CELL_M)
steep = np.degrees(np.arctan(np.hypot(gx, gy))) > 35

mat = np.zeros((NK, NI), np.uint8)               # 0 Pavement (urban default)
mat[park_mask] = 2
mat[road_mask] = 1
mat[steep & ~road_mask] = 4
mat[sea | inland] = 3

# north-up -> south-up rows (k = 0 at the south edge)
h_s, mat_s = h[::-1], mat[::-1]
q = np.round((h_s - ZMIN) / (ZMAX - ZMIN) * 65535).astype("<u2")
ntile = 0
for tk in range(math.ceil(NK / TILE)):
    for ti in range(math.ceil(NI / TILE)):
        hs = q[tk * TILE:(tk + 1) * TILE, ti * TILE:(ti + 1) * TILE]
        ms = mat_s[tk * TILE:(tk + 1) * TILE, ti * TILE:(ti + 1) * TILE]
        rows, cols = hs.shape
        with open(TER / f"tile_{ti}_{tk}.bin", "wb") as f:
            f.write(np.array([cols, rows], "<u2").tobytes())
            f.write(np.ascontiguousarray(hs).tobytes())
            f.write(np.ascontiguousarray(ms).tobytes())
        ntile += 1

# ------------------------------------------------------------ water rectangles
# Water masks on a 32-stud (8.96 m) grid via reprojection (max = "any cell flooded").
# Coarse is fine: where a rectangle overshoots onto dry ground, that ground is above the
# water plane by definition, so the terrain hides the overshoot.
WS = 32
W_M = WS / STUDS_PER_METER
WI, WK = int((R - L) // W_M), int((T - B) // W_M)
wt = from_origin(L, B + WK * W_M, W_M, W_M)


def coarse(a, how=Resampling.max):
    out = np.zeros((WK, WI), np.float32)
    reproject(a.astype(np.float32), out, src_transform=GRID_TRANSFORM, src_crs=CRS_METRIC,
              dst_transform=wt, dst_crs=CRS_METRIC, resampling=how)
    return out[::-1] > 0  # south-up


def greedy(mask):
    """Merge a boolean grid (rows = k from south, cols = i) into rectangles, in studs."""
    m = mask.copy()
    rects = []
    K, I = m.shape
    for k in range(K):
        i = 0
        while i < I:
            if not m[k, i]:
                i += 1
                continue
            j = i
            while j < I and m[k, j]:
                j += 1
            k2 = k + 1
            while k2 < K and m[k2, i:j].all():
                k2 += 1
            m[k:k2, i:j] = False
            # studs: X = WS*i .. WS*j ; Z = -WS*k2 .. -WS*k
            rects.append([WS * i, -WS * k2, WS * j, -WS * k])
            i = j
    return rects


sea_c = coarse(read(HAZ / "sea_mask.tif"), Resampling.average)
inland_c = coarse(read(HAZ / "inland_water.tif"), Resampling.average)
water = dict(cell_studs=WS, sea=greedy(sea_c), inland=greedy(inland_c & ~sea_c),
             inland_level_m=round(float(np.median(dem[read(HAZ / "inland_water.tif") > 0])) + 0.05, 3),
             flood={})
for sid in SCENARIO_IDS:
    fl = coarse(read(PROC / f"flood_depth_{sid}.tif") > 0) & ~sea_c
    water["flood"][sid] = greedy(fl)
(OUT / "water.json").write_text(json.dumps(water, separators=(",", ":")))

man = json.loads((OUT / "manifest.json").read_text())
man["terrain_tiles"] = dict(dir="terrain", tile_cols=TILE, ni=NI, nk=NK, tiles_i=math.ceil(NI / TILE),
                            tiles_k=math.ceil(NK / TILE), voxel_studs=VOX_STUDS, zmin_m=ZMIN, zmax_m=ZMAX,
                            materials=["Pavement", "Asphalt", "Grass", "Mud", "Rock"],
                            layout="u16 cols,u16 rows,u16 h[rows*cols],u8 mat[rows*cols]; rows from south")
man["water"] = "water.json"
(OUT / "manifest.json").write_text(json.dumps(man, indent=1))

tot = sum(f.stat().st_size for f in TER.glob("*.bin"))
print(f"terrain: {NI} x {NK} voxel columns in {ntile} tiles ({tot / 1e6:.1f} MB); "
      f"materials {np.bincount(mat.ravel(), minlength=5).tolist()}")
print(f"water rects: sea {len(water['sea'])}, inland {len(water['inland'])}, "
      + ", ".join(f"{k} {len(v)}" for k, v in water["flood"].items()))
