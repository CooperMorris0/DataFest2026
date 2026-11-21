"""Fetch the USGS 3DEP 1 m LiDAR DEM (Alameda County 2021) clipped to the bbox.

Uses the USGS TNM Access API to find tiles, then reads only the bbox window from the
cloud-optimized GeoTIFFs and merges with rasterio.merge (no hand stitching).
Output: data/raw/dem_1m_navd88.tif (EPSG:26910, meters NAVD88).
"""
import json

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.merge import merge

from config import BBOX, CRS_METRIC, GRID_BOUNDS, RAW, USER_AGENT

PROJECT = "CA_AlamedaCounty_2021_B21"
meta_path = RAW / "tnm_products.json"
out = RAW / "dem_1m_navd88.tif"

if not meta_path.exists():
    r = requests.get(
        "https://tnmaccess.nationalmap.gov/api/v1/products",
        params={"datasets": "Digital Elevation Model (DEM) 1 meter",
                "bbox": f"{BBOX['west']},{BBOX['south']},{BBOX['east']},{BBOX['north']}",
                "prodFormats": "GeoTIFF", "max": 50},
        headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    meta_path.write_text(json.dumps(r.json(), indent=1))

items = json.loads(meta_path.read_text())["items"]
urls = sorted(i["downloadURL"] for i in items if PROJECT in i["downloadURL"])
print("tiles:", *urls, sep="\n  ")

# bbox -> UTM bounds, snapped outward to whole meters
tf = Transformer.from_crs("EPSG:4326", CRS_METRIC, always_xy=True)
xs, ys = zip(*[tf.transform(x, y) for x in (BBOX["west"], BBOX["east"])
               for y in (BBOX["south"], BBOX["north"])])
bounds = (np.floor(min(xs)), np.floor(min(ys)), np.ceil(max(xs)), np.ceil(max(ys)))
print("UTM bounds:", bounds, "size m:", bounds[2] - bounds[0], bounds[3] - bounds[1])

if not out.exists():
    with rasterio.Env(GDAL_HTTP_USERAGENT=USER_AGENT, GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        srcs = [rasterio.open("/vsicurl/" + u) for u in urls]
        nodata = srcs[0].nodata
        arr, transform = merge(srcs, bounds=bounds, res=1.0, nodata=nodata, method="first")
        profile = srcs[0].profile
        for s in srcs:
            s.close()
    profile.update(height=arr.shape[1], width=arr.shape[2], transform=transform,
                   compress="deflate", predictor=3, tiled=True, blockxsize=512, blockysize=512,
                   nodata=nodata, driver="GTiff", BIGTIFF="IF_SAFER")
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(arr)

with rasterio.open(out) as d:
    a = d.read(1, masked=True)
    print("DEM", d.shape, d.crs, "nodata frac %.3f" % a.mask.mean(),
          "min %.2f p1 %.2f p50 %.2f max %.2f" % (a.min(), np.percentile(a.compressed(), 1),
                                                  np.median(a.compressed()), a.max()))
