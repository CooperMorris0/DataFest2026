"""Equity overlay: join flood results to census tracts and CalEnviroScreen 4.0, write stats.json.

Sources (cached in data/raw/):
  * CalEnviroScreen 4.0 results (OEHHA's ArcGIS service; 2010 tract geography): scores and
    tract demographics (race/ethnicity, poverty, linguistic isolation, age)
  * 2020 Census tracts with POP100 (TIGERweb tigerWMS_Census2020, layer 6)
  * 2020 Incorporated Places (TIGERweb layer 26): city tags + Oakland boundary for the baseline

Population allocation (an estimate):
  tract population inside bbox = POP100 * (tract land area inside bbox / tract land area),
  allocated to residential buildings (parcel land use, see 03) in proportion to
  footprint area x height (floor-area proxy). Residents affected = sum over flooded buildings.
High burden = CalEnviroScreen 4.0 statewide percentile >= 75 (top quartile).

Equity baselines: share of residents in high-burden tracts for (a) the study area,
(b) the City of Oakland, (c) Alameda County. "Representation ratio" = share among affected
residents / share in the baseline population (1.0 = proportional).
"""
import json
from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from shapely.geometry import box

from config import (BBOX, CRS_METRIC, DEM_NVA95_M, MHHW_NAVD88_M, NOAA_STATION, PROC, RAW,
                    ROAD_IMPASSABLE_DEPTH_M, SCENARIOS, SURGE_100YR_M, USER_AGENT)

HIGH = 75
CES_URL = ("https://services1.arcgis.com/PCHfdHz4GlDNAhBb/arcgis/rest/services/"
           "CalEnviroScreen_4_0_Results_/FeatureServer/0/query")
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer"
ENV = f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}"
DEMO = {"Hispanic_pct": "Hispanic/Latino", "African_American_pct": "Black/African American",
        "Asian_American_pct": "Asian American", "White_pct": "White",
        "Other_Multiple_pct": "Other/multiple", "pov": "Below 2x poverty line",
        "ling": "Linguistically isolated households", "Elderly_65over_pct": "Age 65+",
        "Children_under10_pct": "Under age 10"}


def arcgis(name, url, **params):
    f = RAW / f"{name}.geojson"
    if not f.exists():
        q = dict(outFields="*", outSR=4326, f="geojson")
        q.update(params)
        feats, offset = [], 0
        while True:
            r = requests.get(url, params=dict(q, resultOffset=offset),
                             headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            page = r.json()
            assert "features" in page, str(page)[:300]
            feats += page["features"]
            if not page.get("properties", {}).get("exceededTransferLimit") and \
                    not page.get("exceededTransferLimit"):
                break
            offset += len(page["features"])
        f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    g = gpd.read_file(f).to_crs(CRS_METRIC)
    print(f"{name}: {len(g)} features")
    return g


env = dict(geometry=ENV, geometryType="esriGeometryEnvelope", inSR=4326,
           spatialRel="esriSpatialRelIntersects")
ces = arcgis("ces4", CES_URL, **env)
ces_county = arcgis("ces4_alameda_county", CES_URL, where="tract >= 6001000000 AND tract < 6002000000")
tracts = arcgis("tracts2020", f"{TIGER}/6/query", **env)
places = arcgis("places2020", f"{TIGER}/26/query", **env)
oakland = arcgis("place_oakland", f"{TIGER}/26/query", where="GEOID='0653000'")

for c in (ces, ces_county):
    for col in ["CIscoreP", "ACS2019TotalPop"] + list(DEMO):
        c[col] = pd.to_numeric(c[col], errors="coerce")
        c.loc[c[col] < 0, col] = np.nan  # OEHHA uses -999 for "no data"
tracts["POP100"] = pd.to_numeric(tracts["POP100"])

flood = json.loads((PROC / "flood_model_summary.json").read_text())
b = gpd.read_file(PROC / "buildings_flood.geojson")
roads = gpd.read_file(PROC / "roads_flood.geojson")
with rasterio.open(PROC / "flood_depth_0ft.tif") as d:
    frame = box(*d.bounds)

# ---------------------------------------------------------------- building joins
pts = gpd.GeoDataFrame(b[["bid"]], geometry=b.geometry.representative_point(), crs=CRS_METRIC)


def join(left, right, cols, rename=None):
    j = gpd.sjoin(left, right[cols + ["geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()].drop(columns="index_right")
    return j.rename(columns=rename or {})


pts = join(pts, tracts, ["GEOID", "POP100"])
pts = join(pts, ces, ["tract", "CIscoreP"] + list(DEMO), {"tract": "ces_tract"})
pts = join(pts, places, ["BASENAME"], {"BASENAME": "city"})
b["tract_id"] = pts["GEOID"].values
b["ces_tract"] = pts["ces_tract"].values
b["ces_pctl"] = pts["CIscoreP"].values
b["city"] = pts["city"].fillna("Unincorporated").values
for col in DEMO:
    b[col] = pts[col].values
b["high_burden"] = b["ces_pctl"] >= HIGH

# ---------------------------------------------------------------- population allocation
tracts["land_frac_in_bbox"] = (tracts.geometry.intersection(frame).area / tracts.area).clip(0, 1)
tracts["pop_in_bbox"] = tracts["POP100"] * tracts["land_frac_in_bbox"]
b["floor_proxy"] = np.where(b["residential_candidate"], b["area_m2"] * b["height_m"], 0.0)
tot = b.groupby("tract_id")["floor_proxy"].transform("sum")
popmap = tracts.set_index("GEOID")["pop_in_bbox"]
b["residents_est"] = np.where(tot > 0, b["tract_id"].map(popmap).fillna(0) * b["floor_proxy"] / tot, 0)

# ---------------------------------------------------------------- road -> tract, city
mid = gpd.GeoDataFrame(geometry=roads.geometry.interpolate(0.5, normalized=True), crs=CRS_METRIC)
mid = join(mid, tracts, ["GEOID"])
mid = join(mid, places, ["BASENAME"], {"BASENAME": "city"})
roads["tract_id"] = mid["GEOID"].values
roads["city"] = mid["city"].fillna("Unincorporated").values

b.to_file(PROC / "buildings_final.geojson", driver="GeoJSON")
roads.to_file(PROC / "roads_final.geojson", driver="GeoJSON")


# ---------------------------------------------------------------- baselines
def share_high(pop, pctl):
    ok = pctl.notna()
    return float(pop[ok & (pctl >= HIGH)].sum() / pop[ok].sum())


oak_geom = oakland.geometry.union_all()
ces_oak = ces_county[ces_county.geometry.representative_point().within(oak_geom)]
baseline = {
    "study_area": dict(residents_est=int(b["residents_est"].sum()),
                       share_high_burden=round(share_high(b["residents_est"], b["ces_pctl"]), 3)),
    "oakland": dict(residents_acs2019=int(ces_oak["ACS2019TotalPop"].sum()), n_tracts=len(ces_oak),
                    share_high_burden=round(share_high(ces_oak["ACS2019TotalPop"], ces_oak["CIscoreP"]), 3)),
    "alameda_county": dict(residents_acs2019=int(ces_county["ACS2019TotalPop"].sum()),
                           n_tracts=len(ces_county),
                           share_high_burden=round(share_high(ces_county["ACS2019TotalPop"],
                                                              ces_county["CIscoreP"]), 3)),
}


def composition(w, df):
    """Population-weighted mean of tract demographic % (weights w)."""
    out = {}
    for col, label in DEMO.items():
        ok = df[col].notna() & (w > 0)
        out[label] = round(float(np.average(df.loc[ok, col], weights=w[ok])), 1) if ok.any() else None
    return out


demo_baseline = {
    "study_area": composition(b["residents_est"], b),
    "oakland": composition(ces_oak["ACS2019TotalPop"], ces_oak),
    "alameda_county": composition(ces_county["ACS2019TotalPop"], ces_county),
}


# ---------------------------------------------------------------- per-scenario totals
def totals(bb, rr, with_detail=False):
    out = []
    for sc in SCENARIOS:
        sid = sc["id"]
        fl = bb[f"depth_{sid}"] > 0
        res = bb.loc[fl, "residents_est"]
        s = dict(id=sid, slr_ft=sc["slr_ft"], storm=sc["storm"],
                 water_level_navd88_m=round(sc["water_m"], 3),
                 buildings_flooded=int(fl.sum()),
                 buildings_flooded_range=[int(bb[f"flooded_{sid}_lo"].sum()),
                                          int(bb[f"flooded_{sid}_hi"].sum())],
                 buildings_flooded_high_burden=int((fl & bb["high_burden"]).sum()),
                 residents_affected_est=int(round(res.sum())),
                 residents_affected_range=[int(round(bb.loc[bb[f"flooded_{sid}_lo"], "residents_est"].sum())),
                                           int(round(bb.loc[bb[f"flooded_{sid}_hi"], "residents_est"].sum()))],
                 residents_affected_high_burden_est=int(round(bb.loc[fl & bb["high_burden"], "residents_est"].sum())),
                 road_km_impassable=round(rr.loc[rr[f"impassable_{sid}"], "length_m"].sum() / 1000, 3))
        if with_detail:
            tot_res = res.sum()
            # below ~50 affected residents, shares and ratios are noise: report none
            s["share_affected_high_burden"] = round(s["residents_affected_high_burden_est"] / tot_res, 3) \
                if tot_res >= 50 else None
            if s["share_affected_high_burden"] is not None:
                s["representation_ratio"] = {k: round(float(s["share_affected_high_burden"] / v["share_high_burden"]), 2)
                                             for k, v in baseline.items()}
            s["affected_demographics"] = composition(bb["residents_est"].where(fl, 0), bb) \
                if tot_res >= 50 else None  # too few residents to describe
        out.append(s)
    return out


scen = totals(b, roads, with_detail=True)
for s, f in zip(scen, flood["scenarios"]):
    assert s["id"] == f["id"] and s["buildings_flooded"] == f["buildings_flooded"]
    s["flooded_land_km2"] = f["flooded_land_km2"]
    s["low_but_disconnected_km2"] = f["disconnected_low_km2"]
    s["road_km_impassable_range"] = [f["road_km_impassable_lo"], f["road_km_impassable_hi"]]

by_city = {c: totals(b[b.city == c], roads[roads.city == c]) for c in b["city"].value_counts().index}

# ---------------------------------------------------------------- tract table
rows = []
tix = tracts.set_index("GEOID")
for gid, g in b.groupby("tract_id"):
    t = tix.loc[gid]
    rr = roads[roads.tract_id == gid]
    pct = g["ces_pctl"].median()
    row = dict(tract_id=gid, name=t["NAME"], city=g["city"].mode().iat[0],
               pop_2020=int(t["POP100"]), pop_in_bbox_est=int(round(t["pop_in_bbox"])),
               ces_pctl=None if np.isnan(pct) else round(float(pct), 1),
               high_burden=bool(not np.isnan(pct) and pct >= HIGH), n_buildings=len(g))
    for sc in SCENARIOS:
        sid = sc["id"]
        fl = g[f"depth_{sid}"] > 0
        row[f"bldg_{sid}"] = int(fl.sum())
        row[f"res_{sid}"] = int(round(g.loc[fl, "residents_est"].sum()))
        row[f"road_km_{sid}"] = round(rr.loc[rr[f"impassable_{sid}"], "length_m"].sum() / 1000, 3)
    rows.append(row)
tt = pd.DataFrame(rows).sort_values(["bldg_3ft_100yr", "bldg_5ft"], ascending=False)
tt.to_csv(PROC / "tract_table.csv", index=False)

# ---------------------------------------------------------------- stats.json
stats = dict(
    generated=str(date.today()),
    bbox_wgs84=BBOX, crs=CRS_METRIC, vertical_datum="NAVD88",
    baseline_water=dict(name="MHHW", station=f"NOAA CO-OPS {NOAA_STATION} (Alameda)",
                        epoch="1983-2001", navd88_m=round(MHHW_NAVD88_M, 3)),
    storm=dict(name="1% annual chance (100-year) still-water level", above_mhhw_m=SURGE_100YR_M,
               ci90_m=[0.77, 0.96], source=f"NOAA CO-OPS Extreme Water Levels, {NOAA_STATION}"),
    uncertainty=dict(method="rerun with water level +/- DEM NVA at 95% (uniform-bias bound)",
                     dem_nva95_m=DEM_NVA95_M),
    scenario_ids=[s["id"] for s in SCENARIOS],
    road_impassable_depth_m=ROAD_IMPASSABLE_DEPTH_M,
    high_burden_rule=f"CalEnviroScreen 4.0 statewide percentile >= {HIGH}",
    n_buildings=len(b),
    pct_heights_estimated=round(100 * b["height_estimated"].mean(), 1),
    pct_buildings_residential=round(100 * b["residential_candidate"].mean(), 1),
    road_km_total=round(roads["length_m"].sum() / 1000, 3),
    equity_baselines=baseline,
    demographic_baselines=demo_baseline,
    scenarios=scen,
    by_city=by_city,
    tracts=tt.to_dict(orient="records"),
    noaa_validation=json.loads((PROC / "noaa_validation.json").read_text())
    if (PROC / "noaa_validation.json").exists() else None,
)
(PROC / "stats.json").write_text(json.dumps(stats, indent=1, default=str))

# ---------------------------------------------------------------- console report
pd.set_option("display.width", 220)
cols = ["id", "buildings_flooded", "buildings_flooded_range", "residents_affected_est",
        "residents_affected_range", "share_affected_high_burden", "road_km_impassable"]
print(pd.DataFrame(scen)[cols].to_string(index=False))
print("\nhigh-burden share of residents:", {k: v["share_high_burden"] for k, v in baseline.items()})
for s in scen:
    if s.get("representation_ratio"):
        print(f"  {s['id']:10s} representation ratio {s['representation_ratio']}")
print("\ndemographics (% of residents):")
dem = pd.DataFrame({**{f"base_{k}": v for k, v in demo_baseline.items()},
                    **{f"affected_{s['id']}": s["affected_demographics"] for s in scen
                       if s["id"] in ("5ft", "3ft_100yr", "5ft_100yr") and s["affected_demographics"]}})
print(dem.to_string())
print("\nby city (3ft_100yr):", {c: v[8]["buildings_flooded"] for c, v in by_city.items()})
print("\nTop tracts (3 ft + 100-yr storm):")
print(tt[["tract_id", "city", "ces_pctl", "pop_in_bbox_est", "bldg_5ft", "bldg_3ft_100yr",
          "res_3ft_100yr", "road_km_3ft_100yr"]].head(10).to_string(index=False))
