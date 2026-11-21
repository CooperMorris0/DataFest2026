"""Clean OSM building footprints and estimate heights.

Rules (see project brief, "Data-cleaning rules"):
  * drop phantom footprints: building=roof/canopy/carport, underground (location or layer<0),
    houseboats (they float, so a bathtub model can't flood them), slivers < 8 m^2
  * dedupe: drop any polygon >80% covered by a larger kept polygon (building:part vs outline)
  * height: `height` tag -> `building:levels * 3 m` -> default 6 m (flagged height_estimated)
Output: data/processed/buildings.geojson (EPSG:26910) + alignment_check.png
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from config import CRS_METRIC, PROC, RAW

b = gpd.read_file(RAW / "osm_buildings.geojson").to_crs(CRS_METRIC)
n0 = len(b)
b["geometry"] = b.geometry.make_valid()
b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]

drop = pd.Series(False, index=b.index)
reasons = {}


def flag(mask, why):
    global drop
    mask = mask & ~drop
    reasons[why] = int(mask.sum())
    drop |= mask


btype = b["building"].fillna(b["building:part"]).fillna("yes")
flag(btype.isin(["roof", "canopy", "carport", "no", "ruins", "construction"]), "roof/canopy/etc")
flag(b["location"].fillna("").str.contains("underground"), "underground location")
layer = pd.to_numeric(b["layer"], errors="coerce").fillna(0)
flag(layer < 0, "negative layer")
flag(btype.eq("houseboat"), "houseboat (floats)")
flag(b.area < 8, "sliver < 8 m2")
b = b[~drop].copy()
b["btype"] = btype[b.index]

# --- dedupe: process largest first, drop polygons >80% covered by already-kept ones ----
b["area_m2"] = b.area
b["is_part"] = b["building:part"].notna() & b["building"].isna()
b = b.sort_values(["is_part", "area_m2"], ascending=[True, False]).reset_index(drop=True)
sidx = b.sindex
keep = np.ones(len(b), bool)
for i, geom in enumerate(b.geometry):
    if not keep[i]:
        continue
    for j in sidx.query(geom, predicate="intersects"):
        if j <= i or not keep[j]:
            continue
        g2 = b.geometry.iat[j]
        if g2.intersection(geom).area > 0.8 * g2.area:
            keep[j] = False
reasons["duplicate / covered >80%"] = int((~keep).sum())
b = b[keep].copy()


# --- heights -------------------------------------------------------------------------
def parse_m(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    s = str(v).strip().lower()
    m = re.match(r"^([\d.]+)\s*(m|meters?)?$", s)
    if m:
        return float(m.group(1))
    m = re.match(r"^([\d.]+)\s*(ft|')", s)
    if m:
        return float(m.group(1)) * 0.3048
    return np.nan


h_tag = b["height"].map(parse_m)
lv = pd.to_numeric(b["building:levels"], errors="coerce")
b["height_source"] = np.where(h_tag > 0, "height_tag", np.where(lv > 0, "levels", "default"))
b["height_m"] = np.where(h_tag > 0, h_tag, np.where(lv > 0, lv * 3.0, 6.0))
b["height_estimated"] = b["height_source"] != "height_tag"
b["height_m"] = b["height_m"].clip(2.5, 200)

NONRES = {"industrial", "warehouse", "commercial", "retail", "office", "church", "school",
          "garage", "garages", "shed", "service", "hospital", "public", "university", "parking",
          "hotel", "train_station", "transportation", "civic", "government", "kindergarten",
          "college", "supermarket", "hangar", "storage_tank", "silo", "manufacture", "chapel",
          "fire_station", "sports_hall", "stadium", "toilets", "greenhouse", "boathouse"}
osm_res = ~b["btype"].isin(NONRES)

# Prefer parcel land use (MTC/SFEI Existing Land Use 2020) where a building sits on a parcel.
RES_LU = {"Multifamily Residential", "Single Family Residential", "Mixed Use Residential",
          "Mobile Home Park", "Mixed Use Commercial"}
lu = gpd.read_file(RAW / "landuse_parcels.geojson").to_crs(CRS_METRIC)[["mtc_land_use_category", "geometry"]]
pts = gpd.GeoDataFrame(geometry=b.geometry.representative_point(), crs=CRS_METRIC)
j = gpd.sjoin(pts, lu, how="left", predicate="within")
j = j[~j.index.duplicated()]
b["parcel_land_use"] = j["mtc_land_use_category"]
has_lu = b["parcel_land_use"].notna()
b["residential_candidate"] = np.where(has_lu, b["parcel_land_use"].isin(RES_LU), osm_res)
b["residential_source"] = np.where(has_lu, "parcel_land_use", "osm_tags")
agree = (b.loc[has_lu, "residential_candidate"] == osm_res[has_lu]).mean()
print(f"buildings on a land-use parcel: {has_lu.mean():.1%}; residential: "
      f"{b['residential_candidate'].mean():.1%} (OSM-tag guess would say {osm_res.mean():.1%}; "
      f"agrees with parcels on {agree:.1%})")

b["bid"] = np.arange(len(b))
b = b[["bid", "osm_id", "btype", "name", "height_m", "height_source", "height_estimated",
       "residential_candidate", "residential_source", "parcel_land_use", "area_m2", "geometry"]]
b.to_file(PROC / "buildings.geojson", driver="GeoJSON")

print(f"raw polygons: {n0}")
for k, v in reasons.items():
    print(f"  dropped {v:6d}  {k}")
print(f"kept buildings: {len(b)}")
print("height source:", b["height_source"].value_counts().to_dict(),
      f"-> {100 * b['height_estimated'].mean():.1f}% estimated "
      f"({100 * (b['height_source'] == 'default').mean():.1f}% default 6 m)")
