"""Write Roblox-ready files + stats.json, then validate them.

Frame: EPSG:26910 meters minus the grid's southwest corner (origin 0,0).
Roblox axes: X = east, Z = -north (south positive), Y = up.  Scale: STUDS_PER_METER.
Elevations stay in meters NAVD88 in the files (Luau converts with STUDS_PER_METER), so the
terrain, water levels and building bases share one vertical datum.

data/processed/roblox/
  heightmap.png             16-bit grayscale, <= 2048 px wide; z = zmin + v/65535*(zmax-zmin)
  buildings/cell_<i>_<j>.json  sharded by 1 km cell; per building:
      id, cx, cz, w, d, rot, h, base, est, tract, ces, res,
      depth[6], flooded/cut/deg/contam/low flags as 6-char strings ("010011"), pri[6]
  roads/cell_<i>_<j>.json   polylines [[x,z,elev],...], width_m, imp (6-char flag string)
  facilities.json, contaminated_sites.json, manifest.json
data/processed/stats.json   single source for all UI numbers
"""
import json
import math
import shutil
from collections import defaultdict
from datetime import date

import geopandas as gpd
import numpy as np
from PIL import Image

from common import read
from config import (ART_BRACKET_LEVELS_IN, ART_LEVEL_FOR_FT, CONTAMINATION_BUFFER_M, CRS_METRIC,
                    DEGRADED_FACTOR, DEGRADED_MIN_EXTRA_S, GRID_BOUNDS, HAZ, HIGH_BURDEN_PCTL,
                    MHHW_NAVD88_M, NOAA_STATION, PRIORITY_WEIGHTS, PROC, ROAD_IMPASSABLE_DEPTH_M,
                    SCENARIO_IDS, SCENARIOS_FT, STUDS_PER_METER, water_level_m)

OUT = PROC / "roblox"
if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "buildings").mkdir(parents=True)
(OUT / "roads").mkdir()
X0, Y0 = GRID_BOUNDS[0], GRID_BOUNDS[1]
CELL = 1000.0


def lx(x):
    return round(float(x - X0), 2)


def lz(y):
    return round(float(-(y - Y0)), 2)


def cell_of(x, y):
    return int((x - X0) // CELL), int((y - Y0) // CELL)


def flags(row, prefix):
    return "".join("1" if bool(row[f"{prefix}_{s}"]) else "0" for s in SCENARIO_IDS)


# ------------------------------------------------------------ terrain heightmap
z = read(HAZ / "dem_filled.tif")
H0, W0 = z.shape
wpx = min(2048, W0)
hpx = int(round(H0 * wpx / W0))
zs = np.array(Image.fromarray(z.astype(np.float32)).resize((wpx, hpx), Image.BILINEAR))
zmin, zmax = float(np.floor(zs.min())), float(np.ceil(zs.max()))
v = np.round((zs - zmin) / (zmax - zmin) * 65535).astype(np.uint16)
Image.fromarray(v).save(OUT / "heightmap.png")
terrain = dict(file="heightmap.png", width_px=wpx, height_px=hpx, meters_per_px=round(W0 / wpx, 4),
               elev_min_m=zmin, elev_max_m=zmax, extent_m=[W0, H0])

# ------------------------------------------------------------ buildings
b = gpd.read_file(PROC / "buildings_final.geojson").to_crs(CRS_METRIC)
shards = defaultdict(list)
for r in b.itertuples(index=False):
    row = r._asdict()
    rect = r.geometry.minimum_rotated_rectangle
    cs = list(rect.exterior.coords)[:4]
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    w, d = math.hypot(*e1), math.hypot(*e2)
    rot = math.degrees(math.atan2(e1[1], e1[0]))
    c = rect.centroid
    rec = dict(id=int(r.bid), cx=lx(c.x), cz=lz(c.y), w=round(max(w, 1.0), 2), d=round(max(d, 1.0), 2),
               rot=round(rot, 1), h=round(float(r.height_m), 1), base=round(float(r.base_elev_m), 2),
               est=bool(r.height_estimated), tract=r.tract_id, ces=None if r.ces_pctl != r.ces_pctl else round(r.ces_pctl, 1),
               res=round(float(r.residents_est), 1),
               depth=[round(float(row[f"depth_{s}"]), 2) for s in SCENARIO_IDS],
               flooded=flags(row, "flooded"), cut=flags(row, "cut_off"), deg=flags(row, "degraded"),
               contam=flags(row, "near_contam"), low=flags(row, "lowlying"),
               pri=[round(float(row[f"priority_{s}"]), 3) for s in SCENARIO_IDS])
    shards[cell_of(c.x, c.y)].append(rec)
for (i, j), recs in shards.items():
    (OUT / "buildings" / f"cell_{i}_{j}.json").write_text(json.dumps(recs, separators=(",", ":")))

# ------------------------------------------------------------ roads
roads = gpd.read_file(PROC / "roads_final.geojson").to_crs(CRS_METRIC)
DEFAULT_W = {"motorway": 14, "trunk": 12, "primary": 12, "secondary": 10, "tertiary": 9,
             "residential": 8, "unclassified": 7, "service": 5, "living_street": 5}
rshards = defaultdict(list)
inv_rows, inv_cols = z.shape


def elev_at(x, y):
    c, r = int(x - X0), int(GRID_BOUNDS[3] - y)
    return round(float(z[min(max(r, 0), inv_rows - 1), min(max(c, 0), inv_cols - 1)]), 2)


for r in roads.itertuples(index=False):
    row = r._asdict()
    hwy = str(r.highway).split(";")[0].replace("_link", "")
    try:
        width = float(str(row.get("width")).split(";")[0])
    except (TypeError, ValueError):
        try:
            width = float(str(row.get("lanes")).split(";")[0]) * 3.5
        except (TypeError, ValueError):
            width = DEFAULT_W.get(hwy, 7)
    pts = [[lx(x), lz(y), elev_at(x, y)] for x, y in r.geometry.coords]
    mid = r.geometry.interpolate(0.5, normalized=True)
    rshards[cell_of(mid.x, mid.y)].append(dict(pts=pts, width_m=round(width, 1), hwy=hwy,
                                               elevated=bool(r.elevated_or_tunnel), name=row.get("name") if isinstance(row.get("name"), str) else None,
                                               imp=flags(row, "impassable")))
for (i, j), recs in rshards.items():
    (OUT / "roads" / f"cell_{i}_{j}.json").write_text(json.dumps(recs, separators=(",", ":")))

# ------------------------------------------------------------ points
fac = gpd.read_file(PROC / "facilities_final.geojson").to_crs(CRS_METRIC)
fac = fac[fac["in_study_area"]]
(OUT / "facilities.json").write_text(json.dumps([
    dict(id=r.fid, type=r.ftype, name=r.name, x=lx(r.geometry.x), z=lz(r.geometry.y), elev=elev_at(r.geometry.x, r.geometry.y),
         flooded=flags(r._asdict(), "flooded")) for r in fac.itertuples(index=False)], separators=(",", ":")))
sites = gpd.read_file(PROC / "contaminated_sites_flagged.geojson").to_crs(CRS_METRIC)
sites = sites[sites["in_study_area"]]
(OUT / "contaminated_sites.json").write_text(json.dumps([
    dict(id=r.site_id, name=r.name, source=r.source, category=r.category, case_type=r.case_type,
         x=lx(r.geometry.x), z=lz(r.geometry.y), elev=elev_at(r.geometry.x, r.geometry.y),
         in_flood=flags(r._asdict(), "in_flood"), near_flood=flags(r._asdict(), "near_flood"))
    for r in sites.itertuples(index=False)], separators=(",", ":")))

manifest = dict(buildings=sorted(f"buildings/{p.name}" for p in (OUT / "buildings").glob("*.json")),
                roads=sorted(f"roads/{p.name}" for p in (OUT / "roads").glob("*.json")),
                facilities="facilities.json", contaminated_sites="contaminated_sites.json",
                terrain=terrain, scenario_ids=SCENARIO_IDS, studs_per_meter=STUDS_PER_METER,
                origin_epsg26910=[X0, Y0], axes="X=east, Z=-north, Y=up; elevations in m NAVD88")
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))

# ------------------------------------------------------------ stats.json
eq = json.loads((PROC / "equity_priority.json").read_text())
expo = json.loads((PROC / "exposure_summary.json").read_text())
cons = json.loads((PROC / "consequences_summary.json").read_text())
val = json.loads((PROC / "hazard_validation.json").read_text()) if (PROC / "hazard_validation.json").exists() else None
for s in eq["scenarios"]:
    s["water_level_studs"] = round(s["water_level_navd88_m"] * STUDS_PER_METER, 2)
stats = dict(
    generated=str(date.today()), title="Oakland Flood Consequence Explorer",
    scenario_ids=SCENARIO_IDS, scenarios_ft=SCENARIOS_FT,
    hazard=dict(primary="ART Bay Shoreline Flood Explorer (BCDC) inundation extents",
                art_level_for_ft={str(k): v for k, v in ART_LEVEL_FOR_FT.items()},
                fallback="connected bathtub on USGS 3DEP 1 m LiDAR (used only where no ART level is configured)",
                note_5ft="ART has no 60 in layer; the 5 ft scenario uses ART 66 in (5.5 ft), conservative",
                art_bracket_for_5ft=expo["art_bracket"], art_vs_bathtub=expo["art_vs_bathtub"],
                bathtub_buildings_by_ft=expo["bathtub_buildings_by_ft"],
                bathtub_5ft_buildings=expo["bathtub_buildings_by_ft"]["5"],
                depth_note="Depth estimated as water level minus LiDAR ground inside ART's extent"),
    baseline_water=dict(name="MHHW", station=f"NOAA CO-OPS {NOAA_STATION} (Alameda)", navd88_m=round(MHHW_NAVD88_M, 3)),
    rules=dict(road_impassable_depth_m=ROAD_IMPASSABLE_DEPTH_M, degraded_factor=DEGRADED_FACTOR,
               degraded_min_extra_s=DEGRADED_MIN_EXTRA_S, contamination_buffer_m=CONTAMINATION_BUFFER_M,
               high_burden=f"CalEnviroScreen 4.0 percentile >= {HIGH_BURDEN_PCTL}",
               priority="Exposure x Vulnerability", priority_weights=PRIORITY_WEIGHTS),
    terrain=terrain, studs_per_meter=STUDS_PER_METER,
    n_buildings=len(b), road_km_total=expo["road_km_total"],
    facilities_in_study_area=expo["facilities_in_study_area"],
    population_in_area_est=eq["population_in_area_est"],
    pct_buildings_residential=eq["pct_buildings_residential"], pct_heights_estimated=eq["pct_heights_estimated"],
    scenarios=eq["scenarios"], top_priority=eq["top_priority"],
    equity_baselines=eq["equity_baselines"], demographic_baselines=eq["demographic_baselines"],
    network=cons["network"], validation=val,
)
tt = json.loads(gpd.pd.read_csv(PROC / "tract_table.csv", dtype={"tract_id": str}).to_json(orient="records"))
stats["tracts"] = tt
(PROC / "stats.json").write_text(json.dumps(stats, indent=1, default=str))

# ------------------------------------------------------------ validation
allb = [r for f in (OUT / "buildings").glob("*.json") for r in json.loads(f.read_text())]
W_EXT, H_EXT = GRID_BOUNDS[2] - X0, GRID_BOUNDS[3] - Y0
assert len(allb) == len(b), "building count mismatch"
for r in allb:
    assert all(math.isfinite(v) for v in (r["cx"], r["cz"], r["w"], r["d"], r["h"], r["base"])), r["id"]
    # footprints are filtered by their representative point (step 04); the box-fit center of a
    # large irregular footprint can sit a little past the edge, hence a 10 m tolerance
    TOL = 10
    assert -TOL <= r["cx"] <= W_EXT + TOL and -H_EXT - TOL <= r["cz"] <= TOL, f"building {r['id']} outside frame"
    assert r["w"] > 0 and r["d"] > 0 and r["h"] > 0
    assert len(r["depth"]) == len(SCENARIO_IDS) == len(r["flooded"]) == len(r["pri"])
for k, s in enumerate(eq["scenarios"]):
    n = sum(r["flooded"][k] == "1" for r in allb)
    assert n == s["buildings_flooded"], (s["id"], n, s["buildings_flooded"])
    m = sum(r["cut"][k] == "1" for r in allb)
    assert m == s["buildings_cut_off"], (s["id"], m, s["buildings_cut_off"])
sizes = sorted(((p.stat().st_size, p.name) for p in OUT.rglob("*.json")), reverse=True)
print(f"buildings {len(allb)} in {len(shards)} shards; roads in {len(rshards)} shards; "
      f"facilities {len(fac)}; contaminated sites {len(sites)}")
print("largest files (KB):", [(n, round(s / 1024)) for s, n in sizes[:4]],
      " total MB:", round(sum(s for s, _ in sizes) / 1e6, 2))
print(f"heightmap {wpx}x{hpx} px @ {terrain['meters_per_px']} m/px, elev {zmin}..{zmax} m")
print("validation passed: counts in JSON == stats.json")
