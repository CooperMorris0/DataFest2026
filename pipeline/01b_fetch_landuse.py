"""Fetch parcel-level Existing Land Use 2020 (MTC + SFEI) for the bbox, paginated.

Service: services3.arcgis.com/i2dkYWmb4wHvYPda/.../sfei_elu_2020_rel1/FeatureServer/0
(published by the Bay Area Metropolitan Transportation Commission). Used to decide which
buildings are residential for the population allocation. Output: data/raw/landuse_parcels.geojson
"""
import json

import geopandas as gpd
import requests

from config import BBOX, RAW, USER_AGENT

URL = ("https://services3.arcgis.com/i2dkYWmb4wHvYPda/arcgis/rest/services/"
       "sfei_elu_2020_rel1/FeatureServer/0/query")
out = RAW / "landuse_parcels.geojson"

if not out.exists():
    feats, offset = [], 0
    while True:
        r = requests.get(URL, params=dict(
            geometry=f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}",
            geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects",
            outFields="elu_use_code,elu_description,landuse_detail_description,"
                      "mtc_land_use_category,jurisdiction",
            outSR=4326, f="geojson", resultOffset=offset, resultRecordCount=2000,
            orderByFields="OBJECTID"), headers={"User-Agent": USER_AGENT}, timeout=120)
        r.raise_for_status()
        page = r.json()
        assert "features" in page, str(page)[:300]
        feats += page["features"]
        print(f"  fetched {len(feats)}")
        if len(page["features"]) < 2000 and not page.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += len(page["features"])
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

p = gpd.read_file(out)
print("parcels:", len(p))
print(p["mtc_land_use_category"].value_counts().to_string())
