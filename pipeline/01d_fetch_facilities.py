"""Fetch critical facilities from authoritative public sources (wider NETWORK_BBOX).

  fire_station      City of Oakland GIS, OFD_Basemap layer 5 "OFD - Stations"
  hospital/clinic/  CDPH Licensed & Certified Healthcare Facilities (CalHHS), active licenses
  nursing_facility
  school            California Public Schools 2024-25 (CA Dept. of Education), active
  rail_station      BART stations (City of Oakland GIS org)
  eoc               Emergency Operations Centers (CalOES 2024, via BCDC regional layer)
OSM facilities (01c) are merged in only if that optional download succeeded.
Output: data/raw/facilities.geojson (EPSG:4326) with fid, ftype, name, source.
"""
import json

import geopandas as gpd
import pandas as pd
import requests

from config import CRS_GEO, NETWORK_BBOX, RAW, USER_AGENT

ENV = dict(geometry=f"{NETWORK_BBOX['west']},{NETWORK_BBOX['south']},{NETWORK_BBOX['east']},{NETWORK_BBOX['north']}",
           geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects",
           outFields="*", outSR=4326, f="geojson")
SOURCES = {
    "fire_oakland": "https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/OFD_Basemap/FeatureServer/5",
    "cdph_health": "https://services5.arcgis.com/FlidZxdI0LGC9vAw/arcgis/rest/services/CDPH_LC_Facilities_Data/FeatureServer/0",
    "cde_schools": "https://services3.arcgis.com/fdvHcZVgB2QSRNkL/arcgis/rest/services/SchoolSites2425/FeatureServer/0",
    "bart": "https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/Bart_Stations/FeatureServer/0",
    "eoc": "https://services2.arcgis.com/4Z9x989NrBVrvFwm/arcgis/rest/services/"
           "Critical_Infrastructure_Strategic_Regional_Priorities/FeatureServer/8",
}


def fetch(name):
    f = RAW / f"fac_{name}.geojson"
    if not f.exists():
        feats, offset = [], 0
        while True:
            r = requests.get(SOURCES[name] + "/query", params=dict(ENV, resultOffset=offset),
                             headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            page = r.json()
            assert "features" in page, str(page)[:300]
            feats += page["features"]
            if not (page.get("properties", {}).get("exceededTransferLimit") or page.get("exceededTransferLimit")):
                break
            offset += len(page["features"])
        f.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    g = gpd.read_file(f)
    print(f"{name}: {len(g)} raw")
    return g


rows = []


def add(g, ftype, name_col, source, idcol):
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    for _, r in g.iterrows():
        rows.append(dict(fid=f"{source}:{r[idcol]}", ftype=ftype, name=str(r[name_col]).strip().title(),
                         source=source, geometry=r.geometry))


fire = fetch("fire_oakland")
fire["label"] = "Oakland Fire Station " + fire["STATION"].astype(str)
add(fire, "fire_station", "label", "OFD", "OBJECTID")

h = fetch("cdph_health")
active = h["LICENSE_STATUS_DESCRIPTION"].fillna("").str.upper().str.contains("ACTIVE") | \
    h["FAC_STATUS_TYPE_CODE"].fillna("").str.upper().eq("OPEN")
h = h[active]
print("  CDPH facility types in area:", h["FAC_FDR"].value_counts().head(15).to_dict())
fdr = h["FAC_FDR"].fillna("").str.upper()
add(h[fdr.eq("GENERAL ACUTE CARE HOSPITAL")], "hospital", "FACNAME", "CDPH", "FACID")
add(h[fdr.str.contains("CLINIC")], "clinic", "FACNAME", "CDPH", "FACID")
add(h[fdr.str.contains("SKILLED NURSING|CONGREGATE LIVING|INTERMEDIATE CARE")], "nursing_facility",
    "FACNAME", "CDPH", "FACID")

s = fetch("cde_schools")
s = s[s["Status"].fillna("Active").eq("Active")]
add(s, "school", "SchoolName", "CDE", "CDSCode")

add(fetch("bart"), "rail_station", "NAME", "BART", "OBJECTID")

eoc = fetch("eoc")
add(eoc, "eoc", "NAME", "CalOES", "OBJECTID")

fac = gpd.GeoDataFrame(rows, crs=CRS_GEO)

osm = RAW / "osm_facilities.geojson"
if osm.exists():  # optional OSM extras (only types the authoritative sources lack)
    o = gpd.read_file(osm)
    o = o[o["ftype"].isin(["shelter", "police", "community_center", "bus_stop"])]
    fac = pd.concat([fac, gpd.GeoDataFrame(dict(fid="OSM:" + o["fid"], ftype=o["ftype"],
                                                name=o["name"], source="OSM"), geometry=o.geometry, crs=CRS_GEO)])
fac.to_file(RAW / "facilities.geojson", driver="GeoJSON")
print("facilities by type:", fac["ftype"].value_counts().to_dict())
