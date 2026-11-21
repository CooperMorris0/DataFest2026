"""Fetch contaminated-site locations near the study area from California's public cleanup
databases (official GIS services; the web download pages refuse scripted requests):

  EnviroStor (DTSC): services3.arcgis.com/Oy2JTCD10wkoelxS/.../Envirostor_Public_Data_Export
                     layers 0 cleanupsites, 1 hazardouswastesites
  GeoTracker (State Water Board): gispublic.waterboards.ca.gov/portalserver/rest/services/
                     Hosted/geotracker_sites_download/FeatureServer/371

Keeps open/active cases plus 'managed in place' (certified with contamination left under
O&M or land-use restrictions). Closed cases stay in the raw files for reference.
Query area = study bbox expanded by ~300 m so sites just outside a flooded edge are caught.
Output: data/raw/contaminated_sites.geojson (EPSG:4326): site_id, name, source, case_type, status
"""
import json

import geopandas as gpd
import pandas as pd
import requests

from config import BBOX, CRS_GEO, RAW, USER_AGENT

PAD = 0.0035  # ~300 m
ENV = dict(geometry=f"{BBOX['west'] - PAD},{BBOX['south'] - PAD},{BBOX['east'] + PAD},{BBOX['north'] + PAD}",
           geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects",
           outFields="*", outSR=4326, f="geojson")
SRC = {
    "envirostor_cleanup": "https://services3.arcgis.com/Oy2JTCD10wkoelxS/arcgis/rest/services/Envirostor_Public_Data_Export/FeatureServer/0",
    "envirostor_hazwaste": "https://services3.arcgis.com/Oy2JTCD10wkoelxS/arcgis/rest/services/Envirostor_Public_Data_Export/FeatureServer/1",
    "geotracker": "https://gispublic.waterboards.ca.gov/portalserver/rest/services/Hosted/geotracker_sites_download/FeatureServer/371",
}


def fetch(name):
    f = RAW / f"contam_{name}.geojson"
    if not f.exists():
        feats, offset = [], 0
        while True:
            r = requests.get(SRC[name] + "/query", params=dict(ENV, resultOffset=offset),
                             headers={"User-Agent": USER_AGENT}, timeout=180)
            r.raise_for_status()
            page = r.json()
            assert "features" in page, str(page)[:300]
            feats += page["features"]
            if not (page.get("properties", {}).get("exceededTransferLimit") or page.get("exceededTransferLimit")):
                break
            offset += len(page["features"])
        f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    g = gpd.read_file(f)
    print(f"{name}: {len(g)} sites (all statuses)")
    return g


# Status categories. "managed_in_place" = cleanup certified but contamination left in place
# under operation & maintenance / land-use restrictions: relevant when floodwater or a rising
# water table reaches the site, so it's kept alongside open cases.
def es_category(status):
    s = (status or "").upper()
    if "O&M" in s or "OPERATION & MAINTENANCE" in s or "LAND USE RESTRICTION" in s:
        return "managed_in_place"
    if (s.startswith("ACTIVE") or s.startswith("INACTIVE") or "BACKLOG" in s) and "WITHDRAWN" not in s:
        return "open"
    return "closed"  # Certified, No Further Action, No Action Required, Refer: ...


rows = []
g = fetch("envirostor_cleanup")
print("  status:", g["status"].value_counts().head(14).to_dict())
for _, r in g.iterrows():
    rows.append(dict(site_id=f"EnviroStor:{r['envirostor_id']}", name=str(r["project_name"]).title(),
                     source="EnviroStor (DTSC)", case_type=r["site_type"], status=r["status"],
                     category=es_category(r["status"]), contaminants=r.get("potential_coc"),
                     geometry=r.geometry))
g = fetch("envirostor_hazwaste")  # permitted hazardous-waste facilities (operating)
print("  facility status:", g["facility_status"].value_counts().to_dict())
for _, r in g.iterrows():
    rows.append(dict(site_id=f"EnviroStor-HW:{r['epa_id']}", name=str(r["facility_name"]).title(),
                     source="EnviroStor (DTSC) hazardous waste facility", case_type=r["facility_type"],
                     status=r["facility_status"],
                     category="open" if "CLOSED" not in str(r["facility_status"]).upper() else "closed",
                     contaminants=None, geometry=r.geometry))

g = fetch("geotracker")
print("  status:", g["status"].value_counts().head(12).to_dict())
print("  case types:", g["case_type"].value_counts().head(10).to_dict())
for _, r in g.iterrows():
    st = str(r["status"] or "").upper()
    rows.append(dict(site_id=f"GeoTracker:{r['global_id']}", name=str(r["business_n"]).title(),
                     source="GeoTracker (SWRCB)", case_type=r["case_type"], status=r["status"],
                     category="open" if st.startswith("OPEN") else "closed",
                     contaminants=r.get("potential_"), geometry=r.geometry))

sites = gpd.GeoDataFrame(rows, crs=CRS_GEO)
sites = sites[sites.geometry.notna() & ~sites.geometry.is_empty]
print("all statuses:", sites.groupby(["source", "category"]).size().to_dict())
sites = sites[sites["category"] != "closed"]
sites.to_file(RAW / "contaminated_sites.geojson", driver="GeoJSON")
print("open/active sites kept:", len(sites), sites.groupby(["source"]).size().to_dict())
print(sites["case_type"].value_counts().head(10).to_dict())
