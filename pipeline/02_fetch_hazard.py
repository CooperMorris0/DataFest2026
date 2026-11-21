"""Fetch ART Bay Shoreline Flood Explorer hazard layers for the study area.

Source: the official ART/BCDC MapServer behind explorer.adaptingtorisingtides.org
  (WMS, layers inundation<N> and lowlying<N>, N = inches above MHHW).
The WMS returns rendered images only (GetFeatureInfo exposes no depth values), so we
render each layer onto our exact 1 m analysis grid (EPSG:26910, native CRS of the
inundation layers) and keep the EXTENT:
    1 = inundated (ART "Depth of Flooding": hydrologically connected flooding)
    2 = disconnected low-lying area (below the water level, not connected)
Depth is estimated later (05) from our LiDAR DEM inside ART's extent.

Output: data/processed/hazard/art_<N>in.tif (uint8), data/raw/art_wms/ (tile cache),
        data/raw/art_wms_capabilities.xml (layer list, for provenance).
"""
import io
import math
import time

import numpy as np
import requests
from PIL import Image

from common import GRID_SHAPE, write
from config import ART_BRACKET_LEVELS_IN, ART_LEVEL_FOR_FT, ART_WMS, GRID_BOUNDS, HAZ, RAW, USER_AGENT

TILE = 2048
cache = RAW / "art_wms"
cache.mkdir(exist_ok=True)
H = {"User-Agent": USER_AGENT}

cap = RAW / "art_wms_capabilities.xml"
if not cap.exists():
    r = requests.get(ART_WMS, params=dict(SERVICE="WMS", REQUEST="GetCapabilities"), headers=H, timeout=60)
    r.raise_for_status()
    cap.write_bytes(r.content)
capabilities = cap.read_text()

levels = sorted({v for v in ART_LEVEL_FOR_FT.values() if v is not None} | set(ART_BRACKET_LEVELS_IN))
L, B, R, T = GRID_BOUNDS
rows, cols = GRID_SHAPE
nty, ntx = math.ceil(rows / TILE), math.ceil(cols / TILE)


def render(layer):
    out = np.zeros(GRID_SHAPE, bool)
    for ty in range(nty):
        for tx in range(ntx):
            x0, y1 = L + tx * TILE, T - ty * TILE          # 1 px = 1 m
            w = min(TILE, cols - tx * TILE)
            h = min(TILE, rows - ty * TILE)
            f = cache / f"{layer}_{ty}_{tx}.png"
            if not f.exists():
                r = requests.get(ART_WMS, headers=H, timeout=180, params=dict(
                    SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap", LAYERS=layer, STYLES="",
                    CRS="EPSG:26910", BBOX=f"{x0},{y1 - h},{x0 + w},{y1}", WIDTH=w, HEIGHT=h,
                    FORMAT="image/png", TRANSPARENT="TRUE"))
                r.raise_for_status()
                if not r.headers.get("content-type", "").startswith("image"):
                    raise RuntimeError(f"{layer}: {r.text[:300]}")
                f.write_bytes(r.content)
                time.sleep(0.2)  # be polite to the server
            a = np.array(Image.open(io.BytesIO(f.read_bytes())).convert("RGBA"))
            assert a.shape[:2] == (h, w), (layer, a.shape, h, w)
            out[ty * TILE: ty * TILE + h, tx * TILE: tx * TILE + w] = a[..., 3] > 0
    return out


for n in levels:
    for layer in (f"inundation{n}", f"lowlying{n}"):
        if f"<Name>{layer}</Name>" not in capabilities:
            raise SystemExit(f"ART layer {layer} not offered by the WMS; check ART_LEVEL_FOR_FT")
    inund = render(f"inundation{n}")
    low = render(f"lowlying{n}") & ~inund
    cls = np.where(inund, 1, np.where(low, 2, 0)).astype("uint8")
    write(HAZ / f"art_{n}in.tif", cls)
    print(f"ART {n:3d} in: inundated {inund.sum() / 1e6:6.3f} km2   low-lying (disconnected) "
          f"{low.sum() / 1e6:6.3f} km2   (incl. any open water ART paints)")
