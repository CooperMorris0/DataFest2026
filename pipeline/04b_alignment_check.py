"""Overlay OSM roads + buildings on the DEM hillshade (full bbox) and on Esri World Imagery
(Jack London Square close-up) to check for offsets. Writes data/processed/alignment_check.png."""
import io
import math

import geopandas as gpd
import matplotlib
import numpy as np
import rasterio
import requests
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import CRS_METRIC, PROC, RAW, USER_AGENT

dem = rasterio.open(RAW / "dem_1m_navd88.tif")
roads = gpd.read_file(RAW / "osm_roads.geojson")
bld = gpd.read_file(PROC / "buildings.geojson")


def hillshade(z, az=315, alt=45):
    gy, gx = np.gradient(z)
    slope = np.pi / 2 - np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, al = np.radians(az), np.radians(alt)
    return np.sin(al) * np.sin(slope) + np.cos(al) * np.cos(slope) * np.cos(a - aspect)


# Esri tiles for a Jack London Square close-up (web mercator, z18), cached on disk.
Z = 18
lon0, lat0, lon1, lat1 = -122.2805, 37.7935, -122.2715, 37.7985


def deg2tile(lon, lat, z):
    n = 2 ** z
    return (int((lon + 180) / 360 * n),
            int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n))


def tile2deg(x, y, z):
    n = 2 ** z
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


tx0, ty0 = deg2tile(lon0, lat1, Z)
tx1, ty1 = deg2tile(lon1, lat0, Z)
cache = RAW / "esri_tiles"
cache.mkdir(exist_ok=True)
mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
for x in range(tx0, tx1 + 1):
    for y in range(ty0, ty1 + 1):
        f = cache / f"{Z}_{x}_{y}.jpg"
        if not f.exists():
            r = requests.get("https://server.arcgisonline.com/ArcGIS/rest/services/"
                             f"World_Imagery/MapServer/tile/{Z}/{y}/{x}",
                             headers={"User-Agent": USER_AGENT}, timeout=30)
            r.raise_for_status()
            f.write_bytes(r.content)
        mosaic.paste(Image.open(io.BytesIO(f.read_bytes())), ((x - tx0) * 256, (y - ty0) * 256))
wl, nt = tile2deg(tx0, ty0, Z)
el, sb = tile2deg(tx1 + 1, ty1 + 1, Z)
merc = gpd.GeoSeries.from_xy([wl, el], [sb, nt], crs="EPSG:4326").to_crs("EPSG:3857")

fig, axes = plt.subplots(1, 2, figsize=(22, 10), gridspec_kw={"width_ratios": [1.6, 1]})
ax = axes[0]
z = dem.read(1, masked=True).filled(0)[::2, ::2]
ex = [dem.bounds.left, dem.bounds.right, dem.bounds.bottom, dem.bounds.top]
ax.imshow(hillshade(z), extent=ex, cmap="gray")
bld.boundary.plot(ax=ax, color="orange", lw=0.3)
roads.to_crs(CRS_METRIC).plot(ax=ax, color="cyan", lw=0.5)
ax.set_title("OSM buildings (orange) + roads (cyan) on 1 m LiDAR hillshade")
ax.set_xlim(ex[0], ex[1]); ax.set_ylim(ex[2], ex[3])

ax = axes[1]
ax.imshow(mosaic, extent=[merc.x[0], merc.x[1], merc.y[0], merc.y[1]])
bld.to_crs("EPSG:3857").boundary.plot(ax=ax, color="orange", lw=0.8)
roads.to_crs("EPSG:3857").plot(ax=ax, color="cyan", lw=0.8)
ax.set_xlim(merc.x[0], merc.x[1]); ax.set_ylim(merc.y[0], merc.y[1])
ax.set_title("Jack London Square: OSM over Esri World Imagery")
for a in axes:
    a.set_xticks([]); a.set_yticks([])
fig.savefig(PROC / "alignment_check.png", dpi=90, bbox_inches="tight")
print("wrote alignment_check.png")
