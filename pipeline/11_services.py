"""How flooding affects public and community services (citywide today + sea-level rise in the study area).

Services (City of Oakland only), from verified public sources:
  Health and care      hospitals, nursing homes, dialysis clinics   CDPH licensed facilities (active)
  Emergency            fire stations                                Oakland Fire Department GIS
  Education and youth  public schools                               CA Dept. of Education 2024-25 (active)
                       Head Start sites                             City of Oakland open data h2rc-b7xm (2013)
  Community            library branches                             City of Oakland open data wakt-xmha (2013)
                       senior centers                               City of Oakland open data aahx-6i3p (2013)
                       recreation centers and pools                 City of Oakland open data qyh9-i9dw (2013)
  Transit              BART stations                                BART (City of Oakland GIS org)
The city's 2013 datasets are the latest published; a few of those sites may have moved or closed (assumption).

Exposure per site:
  * Today (rain / storm-drain flooding, FloodWatch): overall risk of the H3 hex the site sits in
    (oakland-flood-vulnerability/outputs/hex_scores.csv, same percentile classes as the FloodWatch map),
    its social vulnerability (CDC SVI), and OAK 311 flood reports within 250 m (about two blocks), 2013-today.
  * Sea-level rise (sites inside the study-area grid only): site_flood_ft = first scenario where the site's
    building footprint (buildings_final.geojson) or, if it has none, its own 1 m cell floods; access_loss_ft =
    first scenario where the nearest local road (roads_final.geojson, freeways excluded, within 200 m) is
    impassable (> 0.15 m deep, as in 05_flood_exposure.py). Empty = not affected up to 5 ft.
    streets_impassable_<ft>ft = share of local street length within 400 m (~5-minute walk) that is impassable,
    since the single nearest road can stay dry while the streets around it flood.
Outputs: data/processed/floodwatch/services.csv, data/processed/floodwatch/services_summary.json,
         oakland-flood-vulnerability/outputs/facilities.geojson (K2: one marker list for the website;
         flooded / access_lost are 6-character per-scenario flags, 0..5 ft)
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box

from common import point_rowcol, read
from config import CRS_GEO, CRS_METRIC, GRID_BOUNDS, PROC, RAW, ROOT, SCENARIO_IDS, SCENARIOS_FT, USER_AGENT

OUT = PROC / "floodwatch"
OUT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": USER_AGENT}
NEAR_M = 250
ACCESS_MAX_M = 200
STREETS_M = 400  # ~5-minute walk: share of street length around a site that is impassable
FREEWAYS = {"motorway", "motorway_link", "trunk", "trunk_link"}

# ------------------------------------------------------------------ Oakland boundary
bpath = RAW / "oakland_place.geojson"
if not bpath.exists():
    r = requests.get("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/"
                     "MapServer/4/query", params={"where": "GEOID='0653000'", "outFields": "NAME,GEOID", "outSR": 4326,
                                                  "f": "geojson"}, headers=H, timeout=120)
    r.raise_for_status()
    bpath.write_text(r.text)
oakland = gpd.read_file(bpath).to_crs(CRS_GEO).geometry.union_all()

# ------------------------------------------------------------------ services
ENV = dict(geometry="{},{},{},{}".format(*oakland.bounds), geometryType="esriGeometryEnvelope", inSR=4326,
           spatialRel="esriSpatialRelIntersects", outFields="*", outSR=4326, f="geojson")
ARCGIS = {  # same verified services as 01d_fetch_facilities.py
    "fire": "https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/OFD_Basemap/FeatureServer/5",
    "cdph": "https://services5.arcgis.com/FlidZxdI0LGC9vAw/arcgis/rest/services/CDPH_LC_Facilities_Data/FeatureServer/0",
    "schools": "https://services3.arcgis.com/fdvHcZVgB2QSRNkL/arcgis/rest/services/SchoolSites2425/FeatureServer/0",
    "bart": "https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/Bart_Stations/FeatureServer/0",
}
SOCRATA = {"library": "wakt-xmha", "senior_center": "aahx-6i3p", "head_start": "h2rc-b7xm", "parks_rec": "qyh9-i9dw"}


def arcgis(name):
    f = RAW / f"svc_{name}.geojson"
    if not f.exists():
        feats, offset = [], 0
        while True:
            page = requests.get(ARCGIS[name] + "/query", params=dict(ENV, resultOffset=offset), headers=H, timeout=120)
            page.raise_for_status()
            page = page.json()
            assert "features" in page, str(page)[:300]
            feats += page["features"]
            if not (page.get("properties", {}).get("exceededTransferLimit") or page.get("exceededTransferLimit")):
                break
            offset += len(page["features"])
        f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    g = gpd.read_file(f)
    return g[g.geometry.notna() & ~g.geometry.is_empty]


def socrata(name):
    f = RAW / f"svc_{name}.json"
    if not f.exists():
        r = requests.get(f"https://data.oaklandca.gov/resource/{SOCRATA[name]}.json", params={"$limit": 5000},
                         headers=H, timeout=120)
        r.raise_for_status()
        f.write_text(r.text)
    rows = [r for r in json.loads(f.read_text()) if isinstance(r.get("location_1"), dict)
            and r["location_1"].get("latitude")]
    addr = [json.loads(r["location_1"].get("human_address") or "{}").get("address", "") for r in rows]
    geom = gpd.points_from_xy([float(r["location_1"]["longitude"]) for r in rows],
                              [float(r["location_1"]["latitude"]) for r in rows])
    return gpd.GeoDataFrame(pd.DataFrame(rows).assign(address=addr), geometry=geom, crs=CRS_GEO)


def col(g, *names):
    for n in names:
        if n in g.columns:
            return g[n].fillna("").astype(str).str.strip()
    return pd.Series("", index=g.index)


def title(s):
    return s.str.title().str.replace(r"\bOf\b", "of", regex=True)


parts = []


def add(g, ftype, name, address, detail="", source="", enrollment=None):
    parts.append(gpd.GeoDataFrame(dict(ftype=ftype, name=name.values, address=address.values,
                                       detail=detail if isinstance(detail, str) else detail.values, source=source,
                                       enrollment=np.nan if enrollment is None else enrollment.values),
                                  geometry=g.geometry.values, crs=CRS_GEO))


g = arcgis("fire")
add(g, "fire_station", "Oakland Fire Station " + col(g, "STATION"), col(g, "ADDRESS"), source="Oakland Fire Dept.")
g = arcgis("cdph")
g = g[col(g, "LICENSE_STATUS_DESCRIPTION").str.upper().str.contains("ACTIVE") | col(g, "FAC_STATUS_TYPE_CODE").str.upper().eq("OPEN")]
kind = col(g, "FAC_FDR").str.upper()
for ftype, mask in [("hospital", kind.eq("GENERAL ACUTE CARE HOSPITAL")), ("nursing_home", kind.eq("SKILLED NURSING FACILITY")),
                    ("dialysis", kind.eq("CHRONIC DIALYSIS CLINIC"))]:
    s = g[mask]
    add(s, ftype, title(col(s, "FACNAME")), title(col(s, "ADDRESS")), source="CDPH")
g = arcgis("schools")
g = g[col(g, "Status").replace("", "Active").eq("Active")]
enroll = pd.to_numeric(g.get("EnrollTotal"), errors="coerce")
add(g, "school", col(g, "SchoolName"), col(g, "Street"),
    pd.Series([f"{int(e):,} students" if pd.notna(e) and e > 0 else "" for e in enroll], index=g.index), source="CDE",
    enrollment=enroll)
g = arcgis("bart")
add(g, "bart", col(g, "NAME_LONG", "NAME"), col(g, "ADDRESS"), source="BART")
g = socrata("library")
add(g, "library", col(g, "branch"), col(g, "address"), source="Oakland open data (2013)")
g = socrata("senior_center")
add(g, "senior_center", col(g, "name"), col(g, "address"), source="Oakland open data (2013)")
g = socrata("head_start")
add(g, "head_start", "Head Start: " + col(g, "name"), col(g, "address"), "Early childhood program", "Oakland open data (2013)")
g = socrata("parks_rec")
s = g[col(g, "facility_type").isin(["Recreation Center", "Pools", "ADA Inclusion Center"])]
add(s, "rec_center", col(s, "parks_and_recreation_facilities"), col(s, "address"),
    col(s, "facility_type").replace("Pools", "Pool"), "Oakland open data (2013)")

CATEGORY = {"hospital": "Health and care", "nursing_home": "Health and care", "dialysis": "Health and care",
            "fire_station": "Emergency", "school": "Education and youth", "head_start": "Education and youth",
            "library": "Community", "senior_center": "Community", "rec_center": "Community", "bart": "Transit"}
svc = pd.concat(parts, ignore_index=True)
svc = svc[svc.geometry.within(oakland)].drop_duplicates(["ftype", "name"]).reset_index(drop=True)
svc["category"] = svc.ftype.map(CATEGORY)
svc["site_id"] = svc.ftype + ":" + svc.name
print("services in Oakland:", svc.ftype.value_counts().to_dict())

# ------------------------------------------------------------------ today: FloodWatch hex + nearby 311 reports
import h3  # noqa: E402

from config import FLOODWATCH_H3_RES  # noqa: E402

hexes = pd.read_csv(ROOT / "oakland-flood-vulnerability" / "outputs" / "hex_scores.csv")
pct = hexes.fvi.rank(pct=True)
CUTS = [(0.9, "Very high"), (0.7, "High"), (0.4, "Moderate"), (0.2, "Low"), (0.0, "Very low")]
hexes["risk"] = [next(n for c, n in CUTS if p >= c) for p in pct]  # same classes as the FloodWatch map
hexes["fvi_pct"] = (pct * 100).round().astype(int)
svc["h3"] = [h3.latlng_to_cell(p.y, p.x, FLOODWATCH_H3_RES) for p in svc.geometry]
svc = svc.merge(hexes[["h3", "fvi", "fvi_pct", "risk", "svi_overall", "flood_reports"]].rename(
    columns={"flood_reports": "hex_flood_reports", "svi_overall": "svi"}), on="h3", how="left")
svc["risk"] = svc.risk.fillna("Not scored")

FLOOD_CATS = ["Storm Drains - Clogged (Flooding)", "Streets/Sidewalks - Pooling Water", "Watershed - Overflow from a Creek"]
fpath = RAW / "oak311_flood_reports.csv"
if not fpath.exists():
    cats = ",".join("'" + c + "'" for c in FLOOD_CATS)
    rows, offset = [], 0
    while True:
        r = requests.get("https://data.oaklandca.gov/resource/quth-gb8e.json", headers=H, timeout=120, params={
            "$select": "requestid,datetimeinit,description,srx,sry", "$where": f"description in ({cats})",
            "$order": "requestid", "$limit": 50000, "$offset": offset})
        r.raise_for_status()
        rows += r.json()
        if len(r.json()) < 50000:
            break
        offset += 50000
    pd.DataFrame(rows).to_csv(fpath, index=False)
rep = pd.read_csv(fpath)
rep = rep[rep.srx.between(-122.6, -121.9) & rep.sry.between(37.6, 38.0)]
rp = gpd.GeoDataFrame(geometry=gpd.points_from_xy(rep.srx, rep.sry), crs=CRS_GEO).to_crs(CRS_METRIC)
sm = svc.to_crs(CRS_METRIC)
site_i, _ = rp.sindex.query(sm.buffer(NEAR_M), predicate="contains")
svc["flood_reports_250m"] = np.bincount(site_i, minlength=len(svc))
print(f"311 flood reports used: {len(rep):,} (through {str(rep.datetimeinit.max())[:10]})")

# ------------------------------------------------------------------ sea-level rise (study-area grid only)
rows_, cols_, on = point_rowcol(sm.geometry.x, sm.geometry.y)
svc["in_study_area"] = on & sm.geometry.within(box(*GRID_BOUNDS)).values
b = gpd.read_file(PROC / "buildings_final.geojson").to_crs(CRS_METRIC)
j = gpd.sjoin(sm[["geometry"]], b[["geometry"] + [f"flooded_{s}" for s in SCENARIO_IDS]], how="left", predicate="within")
j = j[~j.index.duplicated()]
roads = gpd.read_file(PROC / "roads_final.geojson").to_crs(CRS_METRIC)
roads = roads[~roads.highway.astype(str).str.split(";").map(lambda h: bool(set(h) & FREEWAYS))].reset_index(drop=True)
near = gpd.sjoin_nearest(sm[["geometry"]], roads[["geometry"] + [f"impassable_{s}" for s in SCENARIO_IDS]],
                         how="left", max_distance=ACCESS_MAX_M, distance_col="road_dist_m")
near = near[~near.index.duplicated()]
svc["access_road_dist_m"] = near.road_dist_m.round(0).values

# streets around each site: road length within STREETS_M, and which roads they are (for per-scenario shares)
in_area = np.where(svc.in_study_area.values)[0]
ring = gpd.GeoDataFrame(geometry=sm.geometry.iloc[in_area].buffer(STREETS_M).values, crs=CRS_METRIC)
pairs = gpd.sjoin(ring, roads[["geometry"]], how="inner", predicate="intersects")
pairs["len_m"] = [ring.geometry.iat[i].intersection(roads.geometry.iat[k]).length
                  for i, k in zip(pairs.index, pairs.index_right)]
pairs["site"] = in_area[pairs.index]
street_len = pairs.groupby("site").len_m.sum()

site_ft, acc_ft = np.full(len(svc), np.nan), np.full(len(svc), np.nan)
for ft, sid in zip(SCENARIOS_FT, SCENARIO_IDS):
    imp = roads[f"impassable_{sid}"].astype(bool).values[pairs.index_right]
    share = (pairs.len_m * imp).groupby(pairs.site).sum() / street_len
    svc[f"streets_impassable_{sid}"] = svc.index.map(share).astype(float)
    svc.loc[svc.in_study_area, f"streets_impassable_{sid}"] = svc.loc[svc.in_study_area, f"streets_impassable_{sid}"].fillna(0)
    svc[f"streets_impassable_{sid}"] = svc[f"streets_impassable_{sid}"].round(3)
    depth = read(PROC / f"flood_depth_{sid}.tif")
    own = np.zeros(len(svc), bool)
    own[on] = depth[rows_[on], cols_[on]] > 0
    in_bldg = j[f"flooded_{sid}"].notna().values
    wet = np.where(in_bldg, j[f"flooded_{sid}"].fillna(False).astype(bool).values, own) & svc.in_study_area.values
    cut = near[f"impassable_{sid}"].fillna(False).astype(bool).values & svc.in_study_area.values
    svc[f"site_flooded_{sid}"] = wet
    svc[f"access_lost_{sid}"] = cut
    site_ft[np.isnan(site_ft) & wet] = ft
    acc_ft[np.isnan(acc_ft) & cut] = ft
svc["site_flood_ft"] = pd.array(site_ft, dtype="Int64")
svc["access_loss_ft"] = pd.array(acc_ft, dtype="Int64")

# ------------------------------------------------------------------ outputs
svc["lat"], svc["lng"] = svc.geometry.y.round(6), svc.geometry.x.round(6)
cols = ["site_id", "category", "ftype", "name", "address", "detail", "source", "lat", "lng", "h3", "fvi", "fvi_pct",
        "risk", "svi", "hex_flood_reports", "flood_reports_250m", "in_study_area", "access_road_dist_m",
        "site_flood_ft", "access_loss_ft"] + [f"site_flooded_{s}" for s in SCENARIO_IDS] + \
    [f"access_lost_{s}" for s in SCENARIO_IDS] + [f"streets_impassable_{s}" for s in SCENARIO_IDS]
svc[cols].to_csv(OUT / "services.csv", index=False)

# K2: facility markers for the FloodWatch website (one list, same types and risk).
# Flags are 6-character strings, one per scenario (0..5 ft), like the building export shards.
WEBSITE_TYPES = {"hospital", "nursing_home", "dialysis", "fire_station", "school", "bart"}


def flags(r, prefix):
    return "".join("1" if r[f"{prefix}_{s}"] else "0" for s in SCENARIO_IDS)


feats = []
for _, r in svc.iterrows():
    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.lng, r.lat]}, "properties": dict(
        site_id=r.site_id, name=r["name"], ftype=r.ftype, category=r.category, address=r.address, detail=r.detail,
        source=r.source, website_type=r.ftype in WEBSITE_TYPES,
        enrollment=None if pd.isna(r.enrollment) else int(r.enrollment),
        h3=r.h3, risk=r.risk, at_risk=bool(r.risk in ("High", "Very high")),
        flood_reports_250m=int(r.flood_reports_250m), in_study_area=bool(r.in_study_area),
        flooded=flags(r, "site_flooded"), access_lost=flags(r, "access_lost"),
        streets_impassable=[None if pd.isna(r[f"streets_impassable_{s}"]) else float(r[f"streets_impassable_{s}"])
                            for s in SCENARIO_IDS],
        site_flood_ft=None if pd.isna(r.site_flood_ft) else int(r.site_flood_ft),
        access_loss_ft=None if pd.isna(r.access_loss_ft) else int(r.access_loss_ft))})
fac_path = ROOT / "oakland-flood-vulnerability" / "outputs" / "facilities.geojson"
fac_path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, allow_nan=False), encoding="utf-8")
print(f"wrote {fac_path.name}: {len(feats)} sites ({sum(f['properties']['website_type'] for f in feats)} website types)")

high = svc.risk.isin(["High", "Very high"])
by_type = []
for (cat, ft_), g in svc.groupby(["category", "ftype"]):
    hi = high[g.index]
    by_type.append(dict(category=cat, ftype=ft_, sites=len(g), in_high_risk_areas=int(hi.sum()),
                        median_flood_reports_250m=float(g.flood_reports_250m.median()),
                        with_10plus_reports_250m=int((g.flood_reports_250m >= 10).sum()),
                        high_risk_and_high_svi=int((hi & (g.svi >= 0.8)).sum()),
                        in_study_area=int(g.in_study_area.sum()),
                        **{f"site_flooded_{s}": int(g[f"site_flooded_{s}"].sum()) for s in SCENARIO_IDS},
                        **{f"access_lost_{s}": int(g[f"access_lost_{s}"].sum()) for s in SCENARIO_IDS},
                        **{f"streets_25pct_impassable_{s}": int((g[f"streets_impassable_{s}"] >= 0.25).sum())
                           for s in SCENARIO_IDS}))
affected = svc[svc.site_flood_ft.notna() | svc.access_loss_ft.notna() | (svc.streets_impassable_5ft >= 0.1)]
summary = dict(
    n_services=len(svc), near_m=NEAR_M, access_max_m=ACCESS_MAX_M,
    reports_through=str(rep.datetimeinit.max())[:10],
    by_type=by_type,
    slr_affected_sites=[dict(name=r.name, ftype=r.ftype, site_flood_ft=None if pd.isna(r.site_flood_ft) else int(r.site_flood_ft),
                             access_loss_ft=None if pd.isna(r.access_loss_ft) else int(r.access_loss_ft),
                             streets_impassable_4ft=r.streets_impassable_4ft, streets_impassable_5ft=r.streets_impassable_5ft)
                        for r in affected.sort_values("streets_impassable_5ft", ascending=False).itertuples()],
    assumptions=["City library, senior center, Head Start and Parks & Rec datasets were last updated in 2013.",
                 "Nearby flood reports count 311 reports within 250 m; reports depend on who calls 311.",
                 "Access = nearest non-freeway road within 200 m; a site may have other ways in."])
(OUT / "services_summary.json").write_text(json.dumps(summary, indent=2))
print(pd.DataFrame(by_type)[["category", "ftype", "sites", "in_high_risk_areas", "median_flood_reports_250m",
                             "in_study_area", "site_flooded_5ft", "access_lost_5ft", "streets_25pct_impassable_5ft"]
                            ].to_string(index=False))
print(f"wrote {OUT / 'services.csv'} ({len(svc)} sites)")
