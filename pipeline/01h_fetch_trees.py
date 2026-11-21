"""Fetch Oakland street trees (data.oaklandca.gov dataset svwc-9r23, "TreesAlongSidewalks":
species + surveyed point geometry, citywide sidewalk tree survey) inside the study bbox.
(The similar dataset 4jcx-enxf is NOT usable: every row has the same placeholder coordinate.)
Cached in data/raw/.
Output: data/raw/street_trees.geojson (EPSG:4326) with species."""
import json

import geopandas as gpd
import requests
from shapely.geometry import Point

from config import BBOX, CRS_GEO, RAW, USER_AGENT

OUT = RAW / "street_trees.geojson"
URL = "https://data.oaklandca.gov/resource/svwc-9r23.json"
if not OUT.exists():
    rows, off = [], 0
    where = f"within_box(the_geom, {BBOX['north']}, {BBOX['west']}, {BBOX['south']}, {BBOX['east']})"
    while True:
        r = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=120,
                         params={"$where": where, "$limit": 5000, "$offset": off, "$order": "objectid"})
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < 5000:
            break
        off += 5000
    feats = []
    for t in rows:
        try:
            lon, lat = t["the_geom"]["coordinates"]
        except (KeyError, TypeError, ValueError):
            continue
        if str(t.get("stump", "0")) == "1" or str(t.get("tree", "-1")) == "0":
            continue  # stumps / empty wells
        feats.append(dict(objectid=int(t["objectid"]), species=t.get("species") or "Unknown",
                          geometry=Point(lon, lat)))
    gpd.GeoDataFrame(feats, crs=CRS_GEO).to_file(OUT, driver="GeoJSON")
g = gpd.read_file(OUT)
# belt and braces: keep only points inside the bbox
g = g.cx[BBOX["west"]:BBOX["east"], BBOX["south"]:BBOX["north"]]
if len(g) < len(gpd.read_file(OUT)):
    g.to_file(OUT, driver="GeoJSON")
print(f"street trees in bbox: {len(g)}; top species:", g["species"].value_counts().head(8).to_dict())
