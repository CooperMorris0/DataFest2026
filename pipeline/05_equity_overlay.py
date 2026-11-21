"""Equity overlay: join flood results to census tracts and CalEnviroScreen 4.0, write stats.json.

Sources (queried by bbox envelope, cached in data/raw/):
  * CalEnviroScreen 4.0 results (OEHHA's ArcGIS service; 2010 tract geography)
  * 2020 Census tracts with POP100 (TIGERweb tigerWMS_Census2020, layer 6)
  * 2020 Incorporated Places (TIGERweb layer 26) to split Oakland from Alameda/Emeryville

Population allocation (flagged as an estimate):
  tract population inside bbox = POP100 * (tract land area inside bbox / tract land area)
  allocated to residential-candidate buildings in the tract in proportion to footprint area
  x height (a floor-area proxy). Residents affected = sum over flooded residential buildings.
High burden = CalEnviroScreen 4.0 statewide percentile >= 75 (top quartile).
"""
import json
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

from config import (BBOX, CRS_METRIC, MHHW_NAVD88_M, NOAA_STATION, PROC, RAW, SCENARIOS_FT,
                    USER_AGENT, WATER_LEVELS_M, ROAD_IMPASSABLE_DEPTH_M)

ENV = f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}"
SOURCES = {
    "ces4": ("https://services1.arcgis.com/PCHfdHz4GlDNAhBb/arcgis/rest/services/"
             "CalEnviroScreen_4_0_Results_/FeatureServer/0/query",
             "tract,ACS2019TotalPop,CIscore,CIscoreP,PollutionP,PopCharP,County,City"),
    "tracts2020": ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
                   "tigerWMS_Census2020/MapServer/6/query", "GEOID,NAME,POP100,AREALAND"),
    "places2020": ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
                   "tigerWMS_Census2020/MapServer/26/query", "GEOID,NAME,BASENAME"),
}


def fetch(name):
    f = RAW / f"{name}.geojson"
    if not f.exists():
        url, fields = SOURCES[name]
        r = requests.get(url, params=dict(geometry=ENV, geometryType="esriGeometryEnvelope",
                                          inSR=4326, spatialRel="esriSpatialRelIntersects",
                                          outFields=fields, outSR=4326, f="geojson"),
                         headers={"User-Agent": USER_AGENT}, timeout=120)
        r.raise_for_status()
        if '"error"' in r.text[:200]:  # some fields may not exist; retry with all fields
            r = requests.get(url, params=dict(geometry=ENV, geometryType="esriGeometryEnvelope",
                                              inSR=4326, spatialRel="esriSpatialRelIntersects",
                                              outFields="*", outSR=4326, f="geojson"),
                             headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
        f.write_text(r.text)
    g = gpd.read_file(f).to_crs(CRS_METRIC)
    print(f"{name}: {len(g)} features")
    return g


ces = fetch("ces4")
tracts = fetch("tracts2020")
places = fetch("places2020")
ces["CIscoreP"] = pd.to_numeric(ces["CIscoreP"], errors="coerce")
ces.loc[ces["CIscoreP"] < 0, "CIscoreP"] = np.nan  # OEHHA uses -999 for "no score"
tracts["POP100"] = pd.to_numeric(tracts["POP100"])

flood = json.loads((PROC / "flood_model_summary.json").read_text())
b = gpd.read_file(PROC / "buildings_flood.geojson")
roads = gpd.read_file(PROC / "roads_flood.geojson")

# frame = DEM extent (what the flood model actually covered)
import rasterio
with rasterio.open(PROC / "flood_depth_0ft.tif") as d:
    from shapely.geometry import box
    frame = box(*d.bounds)

# ---------------------------------------------------------------- building joins
pts = b.copy()
pts["geometry"] = b.geometry.representative_point()
pts = gpd.sjoin(pts, tracts[["GEOID", "POP100", "geometry"]], how="left", predicate="within") \
    .drop(columns="index_right")
pts = gpd.sjoin(pts, ces[["tract", "CIscoreP", "geometry"]].rename(columns={"tract": "ces_tract"}),
                how="left", predicate="within").drop(columns="index_right")
pts = gpd.sjoin(pts, places[["BASENAME", "geometry"]].rename(columns={"BASENAME": "city"}),
                how="left", predicate="within").drop(columns="index_right")
pts = pts[~pts.index.duplicated()]
pts["city"] = pts["city"].fillna("Unincorporated")
b["tract_id"] = pts["GEOID"].values
b["ces_tract"] = pts["ces_tract"].values
b["ces_pctl"] = pts["CIscoreP"].values
b["city"] = pts["city"].values

# ---------------------------------------------------------------- population allocation
tracts["land_frac_in_bbox"] = (tracts.geometry.intersection(frame).area / tracts.area).clip(0, 1)
tracts["pop_in_bbox"] = tracts["POP100"] * tracts["land_frac_in_bbox"]
b["floor_proxy"] = np.where(b["residential_candidate"], b["area_m2"] * b["height_m"], 0.0)
tot = b.groupby("tract_id")["floor_proxy"].transform("sum")
popmap = tracts.set_index("GEOID")["pop_in_bbox"]
b["residents_est"] = np.where(tot > 0, b["tract_id"].map(popmap).fillna(0) * b["floor_proxy"] / tot, 0)

# ---------------------------------------------------------------- road -> tract
r_mid = roads.copy()
r_mid["geometry"] = roads.geometry.interpolate(0.5, normalized=True)
r_mid = gpd.sjoin(r_mid, tracts[["GEOID", "geometry"]], how="left", predicate="within")
r_mid = r_mid[~r_mid.index.duplicated()]
roads["tract_id"] = r_mid["GEOID"].values
r_mid = gpd.sjoin(r_mid.drop(columns="index_right"),
                  places[["BASENAME", "geometry"]].rename(columns={"BASENAME": "city"}),
                  how="left", predicate="within")
r_mid = r_mid[~r_mid.index.duplicated()]
roads["city"] = r_mid["city"].fillna("Unincorporated").values

b.to_file(PROC / "buildings_final.geojson", driver="GeoJSON")
roads.to_file(PROC / "roads_final.geojson", driver="GeoJSON")

# ---------------------------------------------------------------- per-scenario totals
HIGH = 75
b["high_burden"] = b["ces_pctl"] >= HIGH


def totals(bb, rr):
    out = []
    for ft, W in zip(SCENARIOS_FT, WATER_LEVELS_M):
        fl = bb[f"depth_{ft}ft"] > 0
        out.append(dict(
            slr_ft=ft, water_level_navd88_m=round(W, 3),
            buildings_flooded=int(fl.sum()),
            buildings_flooded_high_burden=int((fl & bb["high_burden"]).sum()),
            residents_affected_est=int(round(bb.loc[fl, "residents_est"].sum())),
            residents_affected_high_burden_est=int(round(bb.loc[fl & bb["high_burden"], "residents_est"].sum())),
            road_km_impassable=round(rr.loc[rr[f"impassable_{ft}ft"], "length_m"].sum() / 1000, 3),
            road_segments_impassable=int(rr[f"impassable_{ft}ft"].sum()),
        ))
    return out


scen = totals(b, roads)
for s, f in zip(scen, flood["scenarios"]):
    s["flooded_land_km2"] = f["flooded_land_km2"]
    s["low_but_disconnected_km2"] = f["disconnected_low_km2"]
    assert s["buildings_flooded"] == f["buildings_flooded"]

by_city = {c: totals(b[b.city == c], roads[roads.city == c])
           for c in b["city"].value_counts().index}

# ---------------------------------------------------------------- tract table
rows = []
for gid, g in b.groupby("tract_id"):
    t = tracts.set_index("GEOID").loc[gid]
    rr = roads[roads.tract_id == gid]
    row = dict(tract_id=gid, name=t["NAME"], pop_2020=int(t["POP100"]),
               pop_in_bbox_est=int(round(t["pop_in_bbox"])),
               ces_pctl=None if np.isnan(g["ces_pctl"].median()) else round(float(g["ces_pctl"].median()), 1),
               city=g["city"].mode().iat[0], n_buildings=len(g))
    row["high_burden"] = bool(row["ces_pctl"] is not None and row["ces_pctl"] >= HIGH)
    for ft in SCENARIOS_FT:
        fl = g[f"depth_{ft}ft"] > 0
        row[f"bldg_{ft}ft"] = int(fl.sum())
        row[f"res_{ft}ft"] = int(round(g.loc[fl, "residents_est"].sum()))
        row[f"road_km_{ft}ft"] = round(rr.loc[rr[f"impassable_{ft}ft"], "length_m"].sum() / 1000, 3)
    rows.append(row)
tt = pd.DataFrame(rows).sort_values(["bldg_5ft", "res_5ft"], ascending=False)
tt.to_csv(PROC / "tract_table.csv", index=False)

# ---------------------------------------------------------------- stats.json
stats = dict(
    generated=str(date.today()),
    bbox_wgs84=BBOX,
    crs=CRS_METRIC,
    vertical_datum="NAVD88",
    baseline=dict(name="MHHW", station=f"NOAA CO-OPS {NOAA_STATION} (Alameda)",
                  epoch="1983-2001", navd88_m=round(MHHW_NAVD88_M, 3)),
    scenarios_ft=SCENARIOS_FT,
    road_impassable_depth_m=ROAD_IMPASSABLE_DEPTH_M,
    high_burden_rule=f"CalEnviroScreen 4.0 statewide percentile >= {HIGH}",
    n_buildings=len(b),
    pct_heights_estimated=round(100 * b["height_estimated"].mean(), 1),
    road_km_total=round(roads["length_m"].sum() / 1000, 3),
    population_in_bbox_est=int(round(b["residents_est"].sum())),
    # baseline for the equity comparison: share of ALL buildings / residents in high-burden tracts
    baseline_share_high_burden=dict(
        buildings=round(float(b["high_burden"].mean()), 3),
        residents=round(float(b.loc[b["high_burden"], "residents_est"].sum() / b["residents_est"].sum()), 3)),
    scenarios=scen,
    by_city=by_city,
    tracts=tt.to_dict(orient="records"),
    noaa_validation=json.loads((PROC / "noaa_validation.json").read_text())
    if (PROC / "noaa_validation.json").exists() else None,
)
(PROC / "stats.json").write_text(json.dumps(stats, indent=1))

pd.set_option("display.width", 200)
print(pd.DataFrame(scen).to_string(index=False))
bs = stats["baseline_share_high_burden"]
print(f"\nhigh-burden share of ALL buildings {bs['buildings']:.0%}, of ALL residents {bs['residents']:.0%}")
for s in scen[3:]:
    print(f"  {s['slr_ft']} ft: high-burden share of flooded buildings "
          f"{s['buildings_flooded_high_burden'] / max(1, s['buildings_flooded']):.0%}, "
          f"of affected residents {s['residents_affected_high_burden_est'] / max(1, s['residents_affected_est']):.0%}")
print("\nby city, 5 ft:", {c: v[-1]["buildings_flooded"] for c, v in by_city.items()})
print(f"\npopulation allocated in bbox: {stats['population_in_bbox_est']:,}")
print("\nTop tracts at 5 ft:")
print(tt[["tract_id", "city", "ces_pctl", "high_burden", "pop_in_bbox_est",
          "bldg_3ft", "bldg_5ft", "res_5ft", "road_km_5ft"]].head(12).to_string(index=False))
