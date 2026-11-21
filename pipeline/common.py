"""Shared helpers: grid, raster loading, and sampling rasters under buildings / along lines."""
import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy import ndimage

from config import GRID_BOUNDS, GRID_RES_M

L, B, R, T_ = GRID_BOUNDS
GRID_TRANSFORM = from_origin(L, T_, GRID_RES_M, GRID_RES_M)
GRID_SHAPE = (int(round((T_ - B) / GRID_RES_M)), int(round((R - L) / GRID_RES_M)))


def read(path):
    with rasterio.open(path) as d:
        assert d.shape == GRID_SHAPE and d.transform.almost_equals(GRID_TRANSFORM), \
            f"{path} is not on the analysis grid"
        return d.read(1)


def write(path, arr, dtype=None, nodata=None):
    arr = arr.astype(dtype or arr.dtype)
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=arr.dtype,
                crs="EPSG:26910", transform=GRID_TRANSFORM, compress="deflate", tiled=True,
                blockxsize=512, blockysize=512, nodata=nodata)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr, 1)


class PolygonSampler:
    """Rasterize polygons once (id per cell) and reduce rasters over each polygon."""

    def __init__(self, geoms):
        self.n = len(geoms)
        self.ids = rasterize(((g, i + 1) for i, g in enumerate(geoms)), out_shape=GRID_SHAPE,
                             transform=GRID_TRANSFORM, fill=0, dtype="int32")
        present = np.zeros(self.n + 1, bool)
        present[np.unique(self.ids)] = True
        inv = ~GRID_TRANSFORM
        self.fallback = 0
        for i in np.where(~present[1:])[0]:  # slivers that catch no cell center
            p = geoms[i].representative_point()
            c, r = inv * (p.x, p.y)
            r, c = int(r), int(c)
            if 0 <= r < GRID_SHAPE[0] and 0 <= c < GRID_SHAPE[1] and self.ids[r, c] == 0:
                self.ids[r, c] = i + 1
                self.fallback += 1
        self.idx = np.arange(1, self.n + 1)

    def max(self, a):
        return np.nan_to_num(ndimage.maximum(a, self.ids, self.idx), nan=0.0)

    def min(self, a):
        return ndimage.minimum(a, self.ids, self.idx)

    def mean(self, a):
        return np.nan_to_num(ndimage.mean(a, self.ids, self.idx), nan=0.0)


class LineSampler:
    """Sample rasters every ~1 m along lines; reduce per line. Points off-grid are ignored."""

    def __init__(self, geoms, step_m=1.0):
        inv = ~GRID_TRANSFORM
        rr, cc, owner = [], [], []
        for k, g in enumerate(geoms):
            n = max(2, int(g.length / step_m))
            pts = [g.interpolate(t, normalized=True) for t in np.linspace(0, 1, n)]
            for p in pts:
                c, r = inv * (p.x, p.y)
                r, c = int(np.floor(r)), int(np.floor(c))
                if 0 <= r < GRID_SHAPE[0] and 0 <= c < GRID_SHAPE[1]:
                    rr.append(r); cc.append(c); owner.append(k)
        self.n = len(geoms)
        self.rr, self.cc, self.owner = np.array(rr, int), np.array(cc, int), np.array(owner, int)
        self.on_grid = np.bincount(self.owner, minlength=self.n) > 0

    def max(self, a, fill=0.0):
        out = np.full(self.n, -np.inf)
        np.maximum.at(out, self.owner, a[self.rr, self.cc])
        out[~self.on_grid] = fill
        return out

    def min(self, a, fill=np.nan):
        out = np.full(self.n, np.inf)
        np.minimum.at(out, self.owner, a[self.rr, self.cc])
        out[~self.on_grid] = fill
        return out


def point_rowcol(xs, ys):
    inv = ~GRID_TRANSFORM
    cols, rows = inv * (np.asarray(xs), np.asarray(ys))
    rows, cols = np.floor(rows).astype(int), np.floor(cols).astype(int)
    ok = (rows >= 0) & (rows < GRID_SHAPE[0]) & (cols >= 0) & (cols < GRID_SHAPE[1])
    return rows, cols, ok
