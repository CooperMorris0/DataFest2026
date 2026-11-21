"""Storm prep: the best shelter sites for people in high-risk areas.

Candidates are library branches, recreation centers / pools, senior centers and public schools from services.csv
(pipeline/11_services.py) that are on safe ground:
  not in a High / Very high risk hex, at most 10 flood reports within 250 m, and (in the sea-level-rise study
  area) not flooded and with < 10% of nearby streets impassable at +5 ft.
Demand = residents of High / Very high risk hexes, weighted by vulnerability (0.5 + SVI). Residents per hex
= tract population / hexes in that tract (an estimate). A site covers hexes whose centers are within 1 km
(about a 15-minute walk). Sites are picked greedily (maximum coverage) until 12 are chosen or nothing new is
covered. High-risk hexes with no safe site within 1 km are reported as gaps.
Assumptions are flagged in storm_prep_summary.json.

Outputs: data/processed/floodwatch/storm_prep_shelters.csv, storm_prep_summary.json,
         oakland-flood-vulnerability/outputs/storm_prep_map.html (from storm_prep_template.html)
"""
import json

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import shape

from config import CRS_GEO, CRS_METRIC, FLOODWATCH_H3_RES, PROC, RAW, ROOT

OUT = PROC / "floodwatch"
FW = ROOT / "oakland-flood-vulnerability"
SHELTER_WALK_M, N_SHELTERS = 1000, 12
SHELTER_TYPES = {"library", "rec_center", "senior_center", "school"}
HIGH = ("High", "Very high")
CUTS = [(0.9, "Very high"), (0.7, "High"), (0.4, "Moderate"), (0.2, "Low"), (0.0, "Very low")]
pct = lambda s: pd.Series(s).rank(pct=True, method="average").values

# ------------------------------------------------------------------ inputs
hx = pd.read_csv(FW / "outputs" / "hex_scores.csv")
score_col = "fvi_base" if "fvi_base" in hx.columns else "fvi"  # flood x vulnerability, without facility factors
p = hx[score_col].rank(pct=True)
hx["risk_c"] = [next(n for c, n in CUTS if v >= c) for v in p]
n_in_tract = hx.groupby("GEOID").h3.transform("size")
hx["residents_est"] = (hx.population / n_in_tract).fillna(0)
hx["svi"] = hx.svi_overall.fillna(hx.svi_overall.median())
hx_area_km2 = h3.average_hexagon_area(FLOODWATCH_H3_RES, unit="km^2")
hx["density"] = hx.residents_est / hx_area_km2
hxi = hx.set_index("h3")
print(f"hexes: {len(hx)}, scored with '{score_col}'")

svc = pd.read_csv(OUT / "services.csv")

# ------------------------------------------------------------------ shelters
s = svc[svc.ftype.isin(SHELTER_TYPES)].copy()
s["risk_c"] = s.h3.map(hxi.risk_c).fillna("Not scored")
slr_ok = ~s.in_study_area.astype(bool) | ((s.streets_impassable_5ft.fillna(0) < 0.10) & s.site_flood_ft.isna())
s["safe"] = ~s.risk_c.isin(HIGH) & (s.flood_reports_250m <= 10) & slr_ok & s.risk_c.ne("Not scored")
cand = s[s.safe].reset_index(drop=True)
cm = gpd.GeoDataFrame(cand, geometry=gpd.points_from_xy(cand.lng, cand.lat), crs=CRS_GEO).to_crs(CRS_METRIC)

dem = hx[hx.risk_c.isin(HIGH)].copy().reset_index(drop=True)
dem["weight"] = dem.residents_est * (0.5 + dem.svi)
cen = gpd.GeoDataFrame(dem, geometry=gpd.points_from_xy([h3.cell_to_latlng(c)[1] for c in dem.h3],
                                                        [h3.cell_to_latlng(c)[0] for c in dem.h3]), crs=CRS_GEO).to_crs(CRS_METRIC)
ci, di = cen.sindex.query(cm.buffer(SHELTER_WALK_M), predicate="contains")
covers = {k: set(di[ci == k]) for k in range(len(cand))}
covered, picks = set(), []
while len(picks) < N_SHELTERS:
    gains = {k: dem.weight.values[list(v - covered)].sum() for k, v in covers.items() if k not in picks}
    if not gains:
        break
    k = max(gains, key=gains.get)
    if gains[k] <= 0:
        break
    new = covers[k] - covered
    picks.append(k)
    covered |= covers[k]
    cand.loc[k, "pick_rank"] = len(picks)
    cand.loc[k, "new_high_risk_hexes"] = len(new)
    cand.loc[k, "new_residents_covered"] = round(dem.residents_est.values[list(new)].sum())
cand["high_risk_hexes_within_1km"] = [len(covers[k]) for k in range(len(cand))]
cand["high_risk_residents_within_1km"] = [round(dem.residents_est.values[list(covers[k])].sum()) for k in range(len(cand))]
cand = pd.DataFrame(cand.drop(columns="geometry", errors="ignore"))
sh_cols = ["pick_rank", "site_id", "ftype", "name", "address", "detail", "lat", "lng", "h3", "risk_c", "flood_reports_250m",
           "in_study_area", "streets_impassable_5ft", "high_risk_hexes_within_1km", "high_risk_residents_within_1km",
           "new_high_risk_hexes", "new_residents_covered"]
cand[sh_cols].sort_values(["pick_rank", "high_risk_residents_within_1km"], ascending=[True, False]).to_csv(
    OUT / "storm_prep_shelters.csv", index=False)
gaps = dem[~dem.index.isin(set().union(*covers.values()))]
gap_cover_all = dem.index.isin(set().union(*covers.values()))
picked = cand[cand.pick_rank.notna()].sort_values("pick_rank")
print(f"safe shelter candidates: {len(cand)} of {len(s)}; picked {len(picked)}; they cover "
      f"{len(covered)} of {len(dem)} high-risk hexes ({dem.residents_est.values[list(covered)].sum():,.0f} of "
      f"{dem.residents_est.sum():,.0f} residents); {len(gaps)} high-risk hexes have no safe site within 1 km")
print(picked[["pick_rank", "name", "ftype", "new_high_risk_hexes", "new_residents_covered"]].to_string(index=False))

summary = dict(
    hex_score_column=score_col,
    shelter_candidates=int(len(s)), safe_candidates=int(len(cand)), shelters_picked=int(len(picked)),
    high_risk_hexes=int(len(dem)), high_risk_residents=round(float(dem.residents_est.sum())),
    covered_hexes=int(len(covered)), covered_residents=round(float(dem.residents_est.values[list(covered)].sum())),
    gap_hexes=int(len(gaps)), gap_residents=round(float(gaps.residents_est.sum())),
    assumptions=["Residents per hex = tract population / hexes in tract (estimate).",
                 "Shelter sites are suggestions: capacity, accessibility and agreements with each site are not checked.",
                 "Library, senior center and Parks & Rec locations come from 2013 city datasets."])
(OUT / "storm_prep_summary.json").write_text(json.dumps(summary, indent=2))

# ------------------------------------------------------------------ 3. map page
hg = json.loads((FW / "outputs" / "hex_scores.geojson").read_text())
keep_hex = set(dem.h3)
gap_set = set(gaps.h3)
hex_feats = []
for f in hg["features"]:
    c = f["properties"]["h3"]
    if c in keep_hex:
        geom = shape(f["geometry"])
        hex_feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
            [[round(x, 5), round(y, 5)] for x, y in geom.exterior.coords]]}, "properties": dict(
            h3=c, risk=hxi.loc[c, "risk_c"], gap=c in gap_set, residents=int(round(hxi.loc[c, "residents_est"])),
            svi=round(float(hxi.loc[c, "svi"]), 2), reports=int(hxi.loc[c, "flood_reports"]))})
outline = gpd.read_file(RAW / "oakland_place.geojson").to_crs(CRS_GEO)
outline_json = json.loads(gpd.GeoSeries([outline.geometry.union_all().simplify(0.0001)], crs=CRS_GEO).to_json())
sh_json = [dict(rank=None if pd.isna(r.pick_rank) else int(r.pick_rank), name=r["name"], ftype=r.ftype, address=r.address,
                detail=r.detail if isinstance(r.detail, str) else "", lat=r.lat, lng=r.lng, risk=r.risk_c,
                reports=int(r.flood_reports_250m), hexes=int(r.high_risk_hexes_within_1km),
                residents=int(r.high_risk_residents_within_1km),
                new_hexes=None if pd.isna(r.new_high_risk_hexes) else int(r.new_high_risk_hexes),
                new_residents=None if pd.isna(r.new_residents_covered) else int(r.new_residents_covered))
           for _, r in cand.iterrows()]
html = ((FW / "storm_prep_template.html").read_text(encoding="utf-8")
        .replace("__SHELTERS__", json.dumps(sh_json, separators=(",", ":")))
        .replace("__HEXES__", json.dumps({"type": "FeatureCollection", "features": hex_feats}, separators=(",", ":")))
        .replace("__OUTLINE__", json.dumps(outline_json, separators=(",", ":")))
        .replace("__SUMMARY__", json.dumps(summary, separators=(",", ":")))
        .replace("__UPDATED__", pd.Timestamp.today().strftime("%B %d, %Y").replace(" 0", " ")))
(FW / "outputs" / "storm_prep_map.html").write_text(html, encoding="utf-8")
print(f"wrote storm_prep_map.html ({len(html) / 1e6:.2f} MB)")
