"""Equity joins, residents, per-scenario totals, and the equity-weighted priority score.

Joins (cached in data/raw/): CalEnviroScreen 4.0 (OEHHA; 2010 tracts; scores + tract
demographics), 2020 Census tracts with POP100 and incorporated places (TIGERweb).

Residents per building (ESTIMATE): tract population inside the study area
(POP100 x tract land share inside it) allocated to residential buildings (MTC/SFEI parcel
land use, step 04) in proportion to footprint area x height (a floor-area proxy).

Priority for tract i and scenario s:
    Exposure_i   = sum_k w_k * norm_k(component_k)       (PRIORITY_WEIGHTS, sum to 1)
       components: share of the tract's buildings flooded; facilities lost (count);
                   share of the tract's residents cut off from emergency services
       norm_k = value / max over tracts in that scenario (0-1; 0 if all zero)
    Vulnerability_i = CalEnviroScreen 4.0 percentile / 100
    Priority_i   = Exposure_i * Vulnerability_i
Tracts with no CalEnviroScreen score (e.g. Port/industrial tracts) are not ranked.

Outputs: buildings_final.geojson, tract_table.csv, equity_priority.json
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box

from config import (BBOX, CRS_METRIC, GRID_BOUNDS, HIGH_BURDEN_PCTL, PRIORITY_WEIGHTS, PROC, RAW,
                    SCENARIO_IDS, TOP_N_PRIORITY, USER_AGENT)

CES_URL = ("https://services1.arcgis.com/PCHfdHz4GlDNAhBb/arcgis/rest/services/"
           "CalEnviroScreen_4_0_Results_/FeatureServer/0/query")
TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer"
ENV = f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}"
DEMO = {"Hispanic_pct": "Hispanic/Latino", "African_American_pct": "Black/African American",
        "Asian_American_pct": "Asian American", "White_pct": "White",
        "Other_Multiple_pct": "Other/multiple", "pov": "Below 2x poverty line",
        "ling": "Linguistically isolated households", "Elderly_65over_pct": "Age 65+",
        "Children_under10_pct": "Under age 10"}
assert abs(sum(PRIORITY_WEIGHTS.values()) - 1) < 1e-9


def arcgis(name, url, **params):
    f = RAW / f"{name}.geojson"
    if not f.exists():
        q = dict(outFields="*", outSR=4326, f="geojson")
        q.update(params)
        feats, offset = [], 0
        while True:
            r = requests.get(url, params=dict(q, resultOffset=offset), headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            page = r.json()
            assert "features" in page, str(page)[:300]
            feats += page["features"]
            if not (page.get("properties", {}).get("exceededTransferLimit") or page.get("exceededTransferLimit")):
                break
            offset += len(page["features"])
        f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return gpd.read_file(f).to_crs(CRS_METRIC)


env = dict(geometry=ENV, geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects")
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

b = gpd.read_file(PROC / "buildings_consequences.geojson").to_crs(CRS_METRIC)
roads = gpd.read_file(PROC / "roads_exposure.geojson").to_crs(CRS_METRIC)
fac = gpd.read_file(PROC / "facilities_consequences.geojson").to_crs(CRS_METRIC)
sites = gpd.read_file(PROC / "contaminated_sites_flagged.geojson").to_crs(CRS_METRIC)
frame = box(*GRID_BOUNDS)


def join(left, right, cols, rename=None):
    j = gpd.sjoin(left, right[cols + ["geometry"]], how="left", predicate="within")
    return j[~j.index.duplicated()].drop(columns="index_right").rename(columns=rename or {})


pts = gpd.GeoDataFrame(geometry=b.geometry.representative_point(), crs=CRS_METRIC)
pts = join(pts, tracts, ["GEOID"])
pts = join(pts, ces, ["CIscoreP"] + list(DEMO))
pts = join(pts, places, ["BASENAME"], {"BASENAME": "city"})
b["tract_id"] = pts["GEOID"].values
b["ces_pctl"] = pts["CIscoreP"].values
b["city"] = pts["city"].fillna("Unincorporated").values
for col in DEMO:
    b[col] = pts[col].values
b["high_burden"] = b["ces_pctl"] >= HIGH_BURDEN_PCTL

tracts["land_frac_in_area"] = (tracts.geometry.intersection(frame).area / tracts.area).clip(0, 1)
tracts["pop_in_area"] = tracts["POP100"] * tracts["land_frac_in_area"]
b["floor_proxy"] = np.where(b["residential_candidate"], b["area_m2"] * b["height_m"], 0.0)
tot = b.groupby("tract_id")["floor_proxy"].transform("sum")
b["residents_est"] = np.where(tot > 0, b["tract_id"].map(tracts.set_index("GEOID")["pop_in_area"]).fillna(0)
                              * b["floor_proxy"] / tot, 0)

for name, g in (("roads", roads), ("fac", fac)):
    mid = gpd.GeoDataFrame(geometry=g.geometry.interpolate(0.5, normalized=True) if name == "roads" else g.geometry,
                           crs=CRS_METRIC)
    mid = join(join(mid, tracts, ["GEOID"]), places, ["BASENAME"], {"BASENAME": "city"})
    g["tract_id"] = mid["GEOID"].values
    g["city"] = mid["city"].fillna("Outside study area" if name == "fac" else "Unincorporated").values

# ------------------------------------------------------------ baselines + demographics
def share_high(pop, pctl):
    ok = pctl.notna()
    return float(pop[ok & (pctl >= HIGH_BURDEN_PCTL)].sum() / pop[ok].sum())


ces_oak = ces_county[ces_county.geometry.representative_point().within(oakland.geometry.union_all())]
baseline = {
    "study_area": dict(share_high_burden=round(share_high(b["residents_est"], b["ces_pctl"]), 3)),
    "oakland": dict(share_high_burden=round(share_high(ces_oak["ACS2019TotalPop"], ces_oak["CIscoreP"]), 3)),
    "alameda_county": dict(share_high_burden=round(share_high(ces_county["ACS2019TotalPop"], ces_county["CIscoreP"]), 3)),
}


def composition(w, df):
    out = {}
    for col, label in DEMO.items():
        ok = df[col].notna() & (w > 0)
        out[label] = round(float(np.average(df.loc[ok, col], weights=w[ok])), 1) if ok.any() else None
    return out


demo_baseline = {"study_area": composition(b["residents_est"], b),
                 "oakland": composition(ces_oak["ACS2019TotalPop"], ces_oak),
                 "alameda_county": composition(ces_county["ACS2019TotalPop"], ces_county)}

# ------------------------------------------------------------ per-scenario totals
fac_in = fac[fac["in_study_area"]]
expo = json.loads((PROC / "exposure_summary.json").read_text())
conseq = json.loads((PROC / "consequences_summary.json").read_text())
R = b["residents_est"]
scen = []
for sid, ex in zip(SCENARIO_IDS, expo["scenarios"]):
    fl, cut, deg, nc = (b[f"flooded_{sid}"], b[f"cut_off_{sid}"], b[f"degraded_{sid}"], b[f"near_contam_{sid}"])
    res_aff = R[fl].sum()
    s = dict(id=sid, slr_ft=ex["slr_ft"], water_level_navd88_m=ex["water_level_navd88_m"],
             hazard_source=ex["source"], art_level_in=ex["art_level_in"],
             flooded_land_km2=ex["flooded_land_km2"], lowlying_km2=ex["lowlying_km2"],
             buildings_flooded=int(fl.sum()), buildings_lowlying_only=ex["buildings_lowlying_only"],
             residents_affected=int(round(res_aff)),
             residents_lowlying_only=int(round(R[b[f"lowlying_{sid}"] & ~fl].sum())),
             facilities_lost=int(fac_in[f"flooded_{sid}"].sum()),
             facilities_lost_list=conseq["facilities"][sid]["list"],
             buildings_cut_off=int(cut.sum()), residents_cut_off=int(round(R[cut].sum())),
             buildings_degraded=int(deg.sum()), residents_degraded=int(round(R[deg].sum())),
             contaminated_sites_near_flooding=conseq["contamination"][sid]["sites_near_flood"],
             contaminated_sites_in_flooding=conseq["contamination"][sid]["sites_in_flood"],
             residents_near_flooded_contamination=int(round(R[nc].sum())),
             road_km_impassable=ex["road_km_impassable"],
             residents_affected_high_burden=int(round(R[fl & b["high_burden"]].sum())))
    s["share_affected_high_burden"] = round(s["residents_affected_high_burden"] / res_aff, 3) if res_aff >= 50 else None
    if s["share_affected_high_burden"] is not None:
        s["representation_ratio"] = {k: round(s["share_affected_high_burden"] / v["share_high_burden"], 2)
                                     for k, v in baseline.items()}
        s["affected_demographics"] = composition(R.where(fl, 0), b)
    scen.append(s)

# ------------------------------------------------------------ tract table + priority
rows = []
tix = tracts.set_index("GEOID")
for gid, g in b.groupby("tract_id"):
    pct = g["ces_pctl"].median()
    row = dict(tract_id=gid, name=tix.at[gid, "NAME"], city=g["city"].mode().iat[0],
               pop_2020=int(tix.at[gid, "POP100"]), pop_in_area_est=int(round(tix.at[gid, "pop_in_area"])),
               ces_pctl=None if np.isnan(pct) else round(float(pct), 1),
               high_burden=bool(not np.isnan(pct) and pct >= HIGH_BURDEN_PCTL), n_buildings=len(g),
               residents_est=int(round(g["residents_est"].sum())))
    for sid in SCENARIO_IDS:
        fl, cut = g[f"flooded_{sid}"], g[f"cut_off_{sid}"]
        row[f"bldg_flooded_{sid}"] = int(fl.sum())
        row[f"res_affected_{sid}"] = int(round(g.loc[fl, "residents_est"].sum()))
        row[f"res_cut_off_{sid}"] = int(round(g.loc[cut, "residents_est"].sum()))
        row[f"facilities_lost_{sid}"] = int(fac_in[(fac_in.tract_id == gid) & fac_in[f"flooded_{sid}"]].shape[0])
        row[f"road_km_{sid}"] = round(roads.loc[(roads.tract_id == gid) & roads[f"impassable_{sid}"], "length_m"].sum() / 1000, 3)
    rows.append(row)
tt = pd.DataFrame(rows)

top = {}
for sid in SCENARIO_IDS:
    comp = pd.DataFrame({
        "flooded_building_share": tt[f"bldg_flooded_{sid}"] / tt["n_buildings"].clip(lower=1),
        "facilities_lost": tt[f"facilities_lost_{sid}"].astype(float),
        "residents_cut_off_share": tt[f"res_cut_off_{sid}"] / tt["residents_est"].clip(lower=1)})
    norm = comp / comp.max().replace(0, np.nan)
    exposure = sum(PRIORITY_WEIGHTS[k] * norm[k].fillna(0) for k in PRIORITY_WEIGHTS)
    vuln = tt["ces_pctl"] / 100
    tt[f"exposure_{sid}"] = exposure.round(3)
    tt[f"priority_{sid}"] = (exposure * vuln).round(3)
    ranked = tt[tt["ces_pctl"].notna() & (tt[f"priority_{sid}"] > 0)].sort_values(f"priority_{sid}", ascending=False)
    top[sid] = [dict(rank=i + 1, tract_id=r.tract_id, name=r["name"], city=r.city, ces_pctl=r.ces_pctl,
                     priority=r[f"priority_{sid}"], exposure=r[f"exposure_{sid}"],
                     buildings_flooded=r[f"bldg_flooded_{sid}"], residents_affected=r[f"res_affected_{sid}"],
                     residents_cut_off=r[f"res_cut_off_{sid}"], facilities_lost=r[f"facilities_lost_{sid}"])
                for i, (_, r) in enumerate(ranked.head(TOP_N_PRIORITY).iterrows())]
    unranked = tt[tt["ces_pctl"].isna() & (exposure > 0)]
    top[sid + "_unranked_exposed_tracts"] = unranked["tract_id"].tolist()
tt = tt.sort_values("priority_4ft", ascending=False)
tt.to_csv(PROC / "tract_table.csv", index=False)
b["priority_tract_" + "dummy"] = 0  # placeholder removed below
b = b.drop(columns=["priority_tract_dummy"])
for sid in SCENARIO_IDS:  # per-building copy of its tract's priority, for the Roblox map mode
    b[f"priority_{sid}"] = b["tract_id"].map(tt.set_index("tract_id")[f"priority_{sid}"]).fillna(0)
b.to_file(PROC / "buildings_final.geojson", driver="GeoJSON")
roads.to_file(PROC / "roads_final.geojson", driver="GeoJSON")
fac.to_file(PROC / "facilities_final.geojson", driver="GeoJSON")

out = dict(scenarios=scen, equity_baselines=baseline, demographic_baselines=demo_baseline,
           top_priority=top, priority_weights=PRIORITY_WEIGHTS,
           population_in_area_est=int(round(R.sum())),
           pct_buildings_residential=round(100 * b["residential_candidate"].mean(), 1),
           pct_heights_estimated=round(100 * b["height_estimated"].mean(), 1))
(PROC / "equity_priority.json").write_text(json.dumps(out, indent=1, default=str))

pd.set_option("display.width", 250)
cols = ["id", "hazard_source", "buildings_flooded", "residents_affected", "facilities_lost", "residents_cut_off",
        "residents_degraded", "contaminated_sites_near_flooding", "residents_near_flooded_contamination",
        "road_km_impassable", "share_affected_high_burden"]
print(pd.DataFrame(scen)[cols].to_string(index=False))
print("\nbaseline high-burden share:", {k: v["share_high_burden"] for k, v in baseline.items()})
for sid in ("3ft", "4ft", "5ft"):
    print(f"\nTop priority {sid}:")
    print(pd.DataFrame(top[sid]).to_string(index=False))
