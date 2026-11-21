"""Fetch Census TIGER/Line 2025 roads for Alameda County (06001), used only for the ring of
road network OUTSIDE the study area so emergency routes can reach facilities just beyond it
(the OSM network for that ring couldn't be downloaded: Overpass refused automated requests).
Output: data/raw/tiger_roads_06001.geojson (clipped to NETWORK_BBOX, EPSG:4326).
"""
import io
import zipfile

import geopandas as gpd
import requests
from shapely.geometry import box

from config import CRS_GEO, NETWORK_BBOX, RAW, USER_AGENT

URL = "https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_06001_roads.zip"
zpath = RAW / "tl_2025_06001_roads.zip"
out = RAW / "tiger_roads_06001.geojson"
if not zpath.exists():
    r = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=300)
    r.raise_for_status()
    zpath.write_bytes(r.content)
if not out.exists():
    g = gpd.read_file(f"zip://{zpath}").to_crs(CRS_GEO)
    nb = box(NETWORK_BBOX["west"], NETWORK_BBOX["south"], NETWORK_BBOX["east"], NETWORK_BBOX["north"])
    g = g[g.intersects(nb)]
    g.to_file(out, driver="GeoJSON")
g = gpd.read_file(out)
print("TIGER road features in network area:", len(g), g["MTFCC"].value_counts().to_dict())
