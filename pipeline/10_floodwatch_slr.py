"""K1: sea-level-rise exposure per FloodWatch H3 hex.

For every H3 hex (FloodWatch's resolution) that covers the study grid, and every scenario
(0-5 ft), report how much of the hex's land floods and the buildings and residents affected.
This lets FloodWatch (oakland-flood-vulnerability/) show "today's rain flooding" next to
"future sea-level-rise flooding" on the same hexes.

Definitions match 05_flood_exposure.py / 07_equity_priority.py exactly, so totals reconcile:
  * flooded land  = 1 m cells with depth > 0 in flood_depth_<ft>ft.tif (open bay and inland
    water are already excluded there). Each cell goes to the hex containing its center.
  * land          = cells that are not sea_mask or inland_water. flooded_share = flooded / land.
  * buildings     = buildings_final.geojson flooded_<ft>ft, assigned to the hex containing the
    building's representative point (always inside the footprint).
  * residents     = sum of residents_est over flooded buildings (an estimate; kept to 2 decimals
    so hex sums reproduce the stats.json total after rounding).
Hexes on the grid edge are only partly covered: land_m2 counts the part inside the grid
(grid_coverage < 1 flags them).

Inputs : data/processed/flood_depth_<ft>ft.tif, hazard/sea_mask.tif, hazard/inland_water.tif,
         buildings_final.geojson, stats.json; oakland-flood-vulnerability/outputs/hex_scores.csv
         (optional, to flag hexes FloodWatch already scores).
Outputs: data/processed/floodwatch/hex_slr.csv (long: one row per hex x scenario; also carries the
         hex's buildings_total and residents_total, so shares can be computed)
         data/processed/floodwatch/hex_slr_check.json (reconciliation against stats.json)
"""
import json

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from pyproj import Transformer
from rasterio.features import rasterize
import shapely
from shapely.geometry import Polygon, box

from common import GRID_SHAPE, GRID_TRANSFORM, read
from config import (CRS_GEO, CRS_METRIC, FLOODWATCH_H3_RES, GRID_BOUNDS, HAZ, PROC, ROOT, SCENARIO_IDS,
                    SCENARIOS_FT)

OUT = PROC / "floodwatch"
OUT.mkdir(parents=True, exist_ok=True)
to_geo = Transformer.from_crs(CRS_METRIC, CRS_GEO, always_xy=True)
to_utm = Transformer.from_crs(CRS_GEO, CRS_METRIC, always_xy=True)


def shp_transform(tf, geom):
    return shapely.transform(geom, lambda xy: np.column_stack(tf(xy[:, 0], xy[:, 1])))

# ------------------------------------------------------------------ hexes covering the grid
grid_utm = box(*GRID_BOUNDS)
grid_geo = shp_transform(to_geo.transform, grid_utm)
seed = set(h3.geo_to_cells(grid_geo.__geo_interface__, FLOODWATCH_H3_RES))
cand = set().union(*(h3.grid_disk(c, 1) for c in seed))  # ring 1 catches edge hexes


def hex_utm(c):
    return shp_transform(to_utm.transform, Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]))


hexes = {c: hex_utm(c) for c in cand}
hexes = {c: g for c, g in hexes.items() if g.intersects(grid_utm)}
cells = sorted(hexes)
idx = {c: i + 1 for i, c in enumerate(cells)}
print(f"{len(cells)} H3 res-{FLOODWATCH_H3_RES} hexes touch the {GRID_SHAPE[1]} x {GRID_SHAPE[0]} m grid")

# every 1 m cell -> hex id (cell-center rule, same as the rest of the pipeline)
hid = rasterize(((hexes[c], idx[c]) for c in cells), out_shape=GRID_SHAPE, transform=GRID_TRANSFORM,
                fill=0, dtype="int32")
assert (hid > 0).all(), "some grid cells are not covered by any hex"
n = len(cells) + 1

not_land = read(HAZ / "sea_mask.tif").astype(bool) | read(HAZ / "inland_water.tif").astype(bool)
land_m2 = np.bincount(hid.ravel(), weights=(~not_land).ravel(), minlength=n)
grid_m2 = np.bincount(hid.ravel(), minlength=n)
hex_area = np.array([0] + [hexes[c].area for c in cells])

# ------------------------------------------------------------------ buildings -> hexes
b = gpd.read_file(PROC / "buildings_final.geojson").to_crs(CRS_METRIC)
pts = gpd.GeoSeries(b.geometry.representative_point(), crs=CRS_METRIC).to_crs(CRS_GEO)
b["h3"] = [h3.latlng_to_cell(p.y, p.x, FLOODWATCH_H3_RES) for p in pts]
missing = set(b.h3) - set(cells)
assert not missing, f"{len(missing)} building hexes are outside the hex set"
b["hid"] = b.h3.map(idx)
bldg_total = np.bincount(b.hid, minlength=n)
res_total = np.bincount(b.hid, weights=b.residents_est, minlength=n)

# ------------------------------------------------------------------ per scenario
stats = json.loads((PROC / "stats.json").read_text())
st = {s["id"]: s for s in stats["scenarios"]}
fw_path = ROOT / "oakland-flood-vulnerability" / "outputs" / "hex_scores.csv"
fw = set(pd.read_csv(fw_path, usecols=["h3"]).h3) if fw_path.exists() else set()

rows, check = [], []
for ft, sid in zip(SCENARIOS_FT, SCENARIO_IDS):
    flooded = read(PROC / f"flood_depth_{sid}.tif") > 0
    fl_m2 = np.bincount(hid.ravel(), weights=flooded.ravel(), minlength=n)
    fb = b[b[f"flooded_{sid}"].astype(bool)]
    nb = np.bincount(fb.hid, minlength=n)
    res = np.bincount(fb.hid, weights=fb.residents_est, minlength=n)
    for c in cells:
        i = idx[c]
        rows.append(dict(h3=c, scenario=sid, slr_ft=ft,
                         flooded_share=round(fl_m2[i] / land_m2[i], 4) if land_m2[i] else None,
                         flooded_land_m2=int(fl_m2[i]), land_m2=int(land_m2[i]),
                         buildings_flooded=int(nb[i]), residents_affected=round(float(res[i]), 2),
                         buildings_total=int(bldg_total[i]), residents_total=round(float(res_total[i]), 2),
                         grid_coverage=round(grid_m2[i] / hex_area[i], 3), in_floodwatch=c in fw))
    s = st[sid]
    chk = dict(scenario=sid,
               buildings_flooded=(int(nb.sum()), s["buildings_flooded"]),
               residents_affected=(int(round(res.sum())), s["residents_affected"]),
               flooded_land_km2=(round(float(fl_m2.sum()) / 1e6, 4), s["flooded_land_km2"]))
    chk["ok"] = bool(all(a == e for a, e in (chk["buildings_flooded"], chk["residents_affected"]))
                     and abs(chk["flooded_land_km2"][0] - chk["flooded_land_km2"][1]) < 1e-4)
    check.append(chk)
    print(f"{sid}: hex sums vs stats.json  buildings {chk['buildings_flooded']}  residents "
          f"{chk['residents_affected']}  land km2 {chk['flooded_land_km2']}  {'OK' if chk['ok'] else 'MISMATCH'}")

df = pd.DataFrame(rows)
keep = df.groupby("h3")[["land_m2", "buildings_flooded"]].transform("max")
df = df[(keep.land_m2 > 0) | (df.groupby("h3")["buildings_flooded"].transform("max") > 0)]
df.to_csv(OUT / "hex_slr.csv", index=False)
(OUT / "hex_slr_check.json").write_text(json.dumps(dict(
    h3_res=FLOODWATCH_H3_RES, n_hexes=int(df.h3.nunique()),
    n_hexes_in_floodwatch=int(df.loc[df.in_floodwatch, "h3"].nunique()),
    scenarios=check), indent=2))
print(f"wrote {OUT / 'hex_slr.csv'}: {df.h3.nunique()} hexes x {len(SCENARIO_IDS)} scenarios "
      f"({df.loc[df.in_floodwatch, 'h3'].nunique()} also in FloodWatch)")
assert all(c["ok"] for c in check), "hex totals do not reconcile with stats.json"
