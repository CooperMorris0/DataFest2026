"""Styled world geometry for the Roblox viewer, as PRIMITIVE lists (the single source for both
the Roblox builder and the headless-Blender previews; tools/blender_preview.py).

Prim = {"s": shape, "p": [x,y,z], "z": [sx,sy,sz], "r": [rx,ry,rz], "m": look, "c": [r,g,b], ...}
  shape: B block, W wedge (high edge on its +Z side), C cylinder (axis = X), K leaf card
  (thin block with a foliage decal on both faces), p/z in studs (X east, Y up, Z = -north),
  r = degrees for CFrame.Angles(rx, ry, rz), look = a MaterialVariant key (see LOOKS) or a plain
  Roblox Material name, optional "t" transparency, "mk" road marking key, "nc" no collision,
  "role" (wall/roof/road/sidewalk/trunk/leaf).
Buildings: one entry per building {"a": attributes (same as 08 + Archetype, BaseColor), "p": [...]}
           p[0] is the wall (carries the attributes); later prims are its roof/details.
Roads: {"a": {Imp, Street, Hwy, Elevated}, "p": [surface, sidewalks...]}. Trees: flat prim lists.

Archetypes (rule-based from parcel land use, OSM type, height, footprint; choices within an
archetype are a deterministic hash of the building id, never random):
  house      siding (Victorian lap siding) or stucco, pastel palette, gable roof (if narrow)
  apartment  stucco or brick, flat roof with cornice cap
  commercial brick storefronts (< 12 m) or concrete office
  tower      >= 30 m: glass curtain wall (offices) or concrete, rooftop mechanical unit
  industrial corrugated metal sheds (industrial / warehouse / transportation / Port)
  civic      brick or concrete (public, institutional, medical, schools, churches)
"""
import json
import math
import zlib
from collections import defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from common import GRID_TRANSFORM, read
from config import CRS_METRIC, GRID_BOUNDS, HAZ, PROC, RAW, STUDS_PER_METER

S = STUDS_PER_METER
X0, Y0 = GRID_BOUNDS[0], GRID_BOUNDS[1]
OUT = PROC / "roblox" / "styled"
for sub in ("buildings", "roads", "trees"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)
    for f in (OUT / sub).glob("*.json"):
        f.unlink()

# MaterialVariant keys -> (base material, texture, normal map, studs per tile). Uploaded by the
# Roblox builder; previews use the same files.
LOOKS = {
    "siding": ("SmoothPlastic", "facade_siding", 3.2), "stucco": ("SmoothPlastic", "facade_stucco", 3.2),
    "brick": ("SmoothPlastic", "facade_brick", 3.2), "concrete": ("SmoothPlastic", "facade_concrete", 3.2),
    "glass": ("SmoothPlastic", "facade_glass", 3.2), "metal": ("SmoothPlastic", "facade_metal", 3.2),
    "shingle": ("SmoothPlastic", "roof_shingle", 2.0), "flatroof": ("SmoothPlastic", "roof_flat", 4.0),
    "sidewalk": ("SmoothPlastic", "sidewalk", 3.2), "storefront": ("SmoothPlastic", "facade_storefront", 3.2),
}
PALETTE = {  # natural colors (multiplied with the near-white textures)
    "siding": [(122, 158, 196), (226, 196, 112), (150, 186, 140), (214, 140, 120), (236, 226, 200),
               (110, 138, 160), (186, 150, 186), (128, 176, 176), (204, 92, 84), (96, 132, 108)],
    "stucco": [(236, 222, 194), (222, 196, 158), (206, 178, 142), (240, 228, 206), (196, 186, 170),
               (228, 190, 166), (210, 214, 190), (230, 210, 150)],
    "brick": [(170, 84, 62), (150, 70, 54), (186, 112, 82), (138, 88, 70), (164, 104, 80)],
    "concrete": [(204, 198, 186), (184, 180, 170), (214, 206, 190), (172, 176, 178)],
    "glass": [(132, 160, 190), (110, 142, 170), (156, 176, 192), (120, 148, 162)],
    "metal": [(170, 178, 184), (148, 160, 168), (196, 186, 166), (128, 140, 156), (186, 166, 134), (156, 172, 160)],
    "storefront": [(60, 70, 64), (120, 40, 38), (40, 56, 86), (70, 52, 40), (30, 30, 34)],
    "shingle": [(64, 64, 70), (88, 66, 56), (100, 90, 80), (56, 60, 66), (112, 72, 60)],
    "flatroof": [(150, 150, 146), (128, 128, 126), (164, 160, 150), (140, 142, 146)],
}


def h32(*k):
    return zlib.crc32("|".join(map(str, k)).encode())


def pick(lst, *k):
    return list(lst[h32(*k) % len(lst)])


def r1(v):
    return round(float(v), 2)


# ------------------------------------------------------------------ inputs
# shard keys (08) -> attribute names the client reads
attrs_cols = {"Flooded": "flooded", "Cut": "cut", "Deg": "deg", "Contam": "contam", "Low": "low"}
recs = []
for f in sorted((PROC / "roblox" / "buildings").glob("cell_*.json")):
    recs += json.loads(f.read_text())
bf = gpd.read_file(PROC / "buildings_final.geojson", columns=["bid", "btype", "parcel_land_use", "name"],
                   ignore_geometry=True).set_index("bid")
z = read(HAZ / "dem_filled.tif")
inv = ~GRID_TRANSFORM


def ground(xm, zm):
    """DEM elevation (m) at local meters (x east, z = -north)."""
    c, r = inv * (X0 + xm, Y0 - zm)
    r = min(max(int(r), 0), z.shape[0] - 1)
    c = min(max(int(c), 0), z.shape[1] - 1)
    return float(z[r, c])


IND_LU = {"Light Industrial and Warehouse", "Heavy Industrial and Utility", "Transportation"}
COM_LU = {"Commercial Office", "Retail and Other Commercial", "Mixed Use Commercial"}
CIV_LU = {"Public and Institutional", "Medical Parks and Hospitals"}
HOUSE_T = {"house", "detached", "semidetached_house", "terrace", "bungalow"}
IND_T = {"industrial", "warehouse", "hangar", "storage_tank", "manufacture", "service", "garage", "garages", "shed"}
CIV_T = {"school", "church", "chapel", "public", "civic", "government", "hospital", "university", "college", "train_station"}


def archetype(r, info):
    h, a = r["h"], r["w"] * r["d"]
    lu, bt = info.get("parcel_land_use") or "", info.get("btype") or "yes"
    if lu in IND_LU or bt in IND_T:
        return "industrial"
    if h >= 30:
        return "tower"
    if lu in CIV_LU or bt in CIV_T:
        return "civic"
    if lu in COM_LU or bt in {"commercial", "retail", "office", "hotel", "supermarket"}:
        return "commercial"
    if a < 350 and h <= 10 and (lu == "Single Family Residential" or bt in HOUSE_T or a < 220):
        return "house"
    return "apartment"


def wall_look(arch, bid, h):
    if arch == "house":
        return "siding" if h32("w", bid) % 10 < 6 else "stucco"  # West Oakland: many Victorians
    if arch == "apartment":
        return "brick" if h32("w", bid) % 10 < 3 else "stucco"
    if arch == "commercial":
        return "brick" if h < 12 else "concrete"
    if arch == "tower":
        return "glass" if h32("w", bid) % 10 < 6 else "concrete"
    if arch == "civic":
        return "brick" if h32("w", bid) % 10 < 6 else "concrete"
    return "metal"


def ang(rot_deg):  # same convention as WorldBuilder: CFrame.Angles(0, rad(rot), 0)
    return math.radians(rot_deg)


def local(cx, cz, rot, dx, dz):
    """offset in the building frame (dx along its X, dz along its Z) -> world studs."""
    a = ang(rot)
    # Roblox: CFrame.Angles(0,a,0) maps local X -> (cos a, 0, -sin a), local Z -> (sin a, 0, cos a)
    return cx + dx * math.cos(a) + dz * math.sin(a), cz - dx * math.sin(a) + dz * math.cos(a)


# ------------------------------------------------------------------ buildings
SINK = 1.0
bshards = defaultdict(list)
arch_count = defaultdict(int)
for r in recs:
    info = bf.loc[r["id"]].to_dict() if r["id"] in bf.index else {}
    arch = archetype(r, info)
    arch_count[arch] += 1
    look = wall_look(arch, r["id"], r["h"])
    wc = pick(PALETTE[look], "c", r["id"])
    cx, cz, rot = r["cx"] * S, r["cz"] * S, r["rot"]
    w, d = r["w"] * S, r["d"] * S
    base_y = (r["base"] - SINK) * S
    hw = (r["h"] + SINK) * S
    top = base_y + hw
    prims = [dict(s="B", p=[r1(cx), r1(base_y + hw / 2), r1(cz)], z=[r1(w), r1(hw), r1(d)], r=[0, r1(rot), 0],
                  m=look, c=wc, role="wall")]
    short_m = min(r["w"], r["d"])
    if arch == "house" and short_m <= 14 and r["h"] < 12:
        # gable: ridge along the long axis. Rotate frame so local X is the long side.
        rr, W_, D_ = (rot, w, d) if r["w"] >= r["d"] else (rot + 90, d, w)
        rise = min(0.38 * short_m, 4.0) * S
        rc = pick(PALETTE["shingle"], "r", r["id"])
        ov = 0.3 * S  # eave overhang
        for sign, extra in ((-1, 0), (1, 180)):
            px, pz = local(cx, cz, rr, 0, sign * D_ / 4)
            prims.append(dict(s="W", p=[r1(px), r1(top + rise / 2), r1(pz)], z=[r1(W_ + ov), r1(rise), r1(D_ / 2 + ov / 2)],
                              r=[0, r1(rr + extra), 0], m="shingle", c=rc, role="roof"))
    else:
        rc = pick(PALETTE["flatroof"], "r", r["id"])
        cap = 0.6 * S if r["h"] >= 8 else 0.35 * S
        lip = (0.5 if r["h"] >= 8 else 0.2) * S
        prims.append(dict(s="B", p=[r1(cx), r1(top + cap / 2), r1(cz)], z=[r1(w + lip), r1(cap), r1(d + lip)],
                          r=[0, r1(rot), 0], m="flatroof", c=rc, role="roof"))
        if arch == "tower":  # rooftop mechanical penthouse
            prims.append(dict(s="B", p=[r1(cx), r1(top + cap + 1.6 * S), r1(cz)], z=[r1(w * 0.4), r1(3.2 * S), r1(d * 0.4)],
                              r=[0, r1(rot), 0], m="concrete", c=[196, 196, 192], role="roof"))
    if arch == "commercial" or (arch == "apartment" and info.get("parcel_land_use") == "Mixed Use Residential"):
        # ground-floor storefront band (one 3.2 m texture tile tall), slightly proud of the wall
        sfh = 3.2 * S
        prims.append(dict(s="B", p=[r1(cx), r1((r["base"]) * S + sfh / 2), r1(cz)], z=[r1(w + 0.35), r1(sfh), r1(d + 0.35)],
                          r=[0, r1(rot), 0], m="storefront", c=pick(PALETTE["storefront"], "s", r["id"]), role="detail"))
    a = {k: r[v] for k, v in attrs_cols.items()}
    a.update(Depth=",".join(map(str, r["depth"])), Pri=",".join(map(str, r["pri"])), Tract=r.get("tract") or "",
             CES=r["ces"] if r.get("ces") is not None else -1, Residents=r["res"], HeightM=r["h"],
             HeightEstimated=r["est"], Archetype=arch, BaseColor=wc, id=r["id"])
    cell = f"cell_{int((r['cx']) // 1000)}_{int((-r['cz']) // 1000)}"
    bshards[cell].append(dict(a=a, p=prims))
for cell, items in bshards.items():
    (OUT / "buildings" / f"{cell}.json").write_text(json.dumps(items, separators=(",", ":"), allow_nan=False))

# ------------------------------------------------------------------ roads (+ sidewalks)
NO_SIDEWALK = {"motorway", "trunk", "service", "living_street"}
rshards = defaultdict(list)
n_side = 0
for f in sorted((PROC / "roblox" / "roads").glob("cell_*.json")):
    for rd in json.loads(f.read_text()):
        w = rd["width_m"] * S
        lanes4 = rd["hwy"] in ("primary", "secondary", "motorway", "trunk") or rd["width_m"] >= 13
        mk = None if rd["hwy"] in ("service", "living_street") else ("4" if lanes4 else "2")
        side = not rd["elevated"] and rd["hwy"] not in NO_SIDEWALK
        for i in range(len(rd["pts"]) - 1):
            a_, b_ = rd["pts"][i], rd["pts"][i + 1]
            pa = np.array([a_[0] * S, a_[2] * S + 0.3, a_[1] * S])
            pb = np.array([b_[0] * S, b_[2] * S + 0.3, b_[1] * S])
            seg = pb - pa
            L = float(np.linalg.norm(seg))
            if L < 0.5:
                continue
            mid = (pa + pb) / 2
            yaw = math.degrees(math.atan2(-seg[0], -seg[2]))   # lookAt: -Z points along the segment
            pitch = math.degrees(math.asin(max(-1, min(1, seg[1] / L))))
            prims = [dict(s="B", p=[r1(v) for v in mid], z=[r1(w), 0.4, r1(L + w * 0.5)], r=[r1(pitch), r1(yaw), 0],
                          m="Asphalt", c=[44, 44, 48], role="road", nc=1, **({"mk": mk} if mk else {}))]
            if side:
                sw = 2.2 * S
                for sgn in (-1, 1):
                    # offset perpendicular to the segment in the horizontal plane
                    perp = np.array([-seg[2], 0, seg[0]]) / max(1e-6, math.hypot(seg[0], seg[2]))
                    c_ = mid + perp * sgn * (w / 2 + sw / 2) + np.array([0, 0.25, 0])
                    prims.append(dict(s="B", p=[r1(v) for v in c_], z=[r1(sw), 0.9, r1(L)], r=[r1(pitch), r1(yaw), 0],
                                      m="sidewalk", c=[204, 202, 196], role="sidewalk"))
                    n_side += 1
            cell = f.stem
            rshards[cell].append(dict(a=dict(Imp=rd["imp"], Street=rd.get("name") or "", Hwy=rd["hwy"],
                                             Elevated=rd["elevated"]), p=prims))
for cell, items in rshards.items():
    (OUT / "roads" / f"{cell}.json").write_text(json.dumps(items, separators=(",", ":"), allow_nan=False))

# ------------------------------------------------------------------ trees
# species -> (group, crown diameter m, height m, crown color)
def tree_kind(sp):
    s = (sp or "").lower()
    if any(k in s for k in ("washingtonia", "phoenix", "syagrus", "trachycarpus", "palm")):
        return "palm", 3.5, 11, (92, 120, 60)
    if any(k in s for k in ("pinus", "cupressus", "sequoia", "cedrus", "podocarpus")):
        return "conifer", 4.5, 12, (46, 84, 52)
    if "platanus" in s:
        return "plane", 9, 13, (88, 122, 62)
    if "magnolia" in s:
        return "magnolia", 6, 9, (52, 92, 52)
    if any(k in s for k in ("lagerstroemia", "prunus serrulata", "cercis", "malus")):
        return "flowering", 4, 6, (196, 112, 150)
    if "prunus cerasifera" in s or "blireiana" in s:
        return "purple", 4.5, 6, (110, 52, 70)
    if "pyrus" in s:
        return "pear", 5, 8, (98, 132, 70)
    if "ginkgo" in s:
        return "ginkgo", 4.5, 9, (150, 160, 70)
    return "broadleaf", 6, 9, (76, 112, 58)


def tree_prims(xm, zm, kind, tid):
    g, cd, ht, col = kind
    j = (h32("t", tid) % 21 - 10) / 100  # +/-10% size, deterministic
    cd, ht = cd * (1 + j), ht * (1 + j)
    y0 = ground(xm, zm) * S
    x, zz = xm * S, zm * S
    trunk_h = ht * (0.75 if g == "palm" else 0.38) * S
    tw = (0.3 if g != "palm" else 0.45) * S
    out = [dict(s="C", p=[r1(x), r1(y0 + trunk_h / 2), r1(zz)], z=[r1(trunk_h), r1(tw), r1(tw)], r=[0, 0, 90],
                m="Wood", c=[92, 74, 58], role="trunk")]
    crown_h = min((ht * S - trunk_h) * (1.0 if g != "palm" else 1.6), cd * S * (1.4 if g == "conifer" else 0.95))
    yc = y0 + trunk_h + crown_h / 2 - (0.25 * crown_h if g == "palm" else 0)
    yaw0 = h32("y", tid) % 90
    for k in range(3):  # three crossed leaf cards (60 degrees apart)
        out.append(dict(s="K", p=[r1(x), r1(yc), r1(zz)], z=[r1(cd * S), r1(crown_h if g != "conifer" else crown_h * 1.15), 0.05],
                        r=[0, r1(yaw0 + 60 * k), 0], m="SmoothPlastic", c=list(col), t=1, d="foliage", nc=1, role="leaf"))
    return out


trees = gpd.read_file(RAW / "street_trees.geojson").to_crs(CRS_METRIC)
tshards = defaultdict(list)
n_tree = 0
for t in trees.itertuples():
    xm, zm = t.geometry.x - X0, -(t.geometry.y - Y0)
    if not (0 <= xm <= GRID_BOUNDS[2] - X0 and -(GRID_BOUNDS[3] - Y0) <= zm <= 0):
        continue
    tshards[f"cell_{int(xm // 1000)}_{int(-zm // 1000)}"] += tree_prims(xm, zm, tree_kind(t.species), t.objectid)
    n_tree += 1

# park trees: deterministic jittered grid (16 m) inside Open Space parcels, away from buildings
lu = gpd.read_file(RAW / "landuse_parcels.geojson").to_crs(CRS_METRIC)
parks = lu[lu["mtc_land_use_category"] == "Open Space"].geometry.union_all().intersection(box(*GRID_BOUNDS))
bldg = gpd.read_file(PROC / "buildings_final.geojson", columns=["geometry"]).to_crs(CRS_METRIC).buffer(4).union_all()
roads_buf = gpd.read_file(PROC / "roads_final.geojson", columns=["geometry"]).to_crs(CRS_METRIC).buffer(6).union_all()
blocked = bldg.union(roads_buf)
n_park = 0
if not parks.is_empty:
    minx, miny, maxx, maxy = parks.bounds
    from shapely.geometry import Point
    from shapely.prepared import prep
    pp, bp = prep(parks), prep(blocked)
    for gx in np.arange(minx, maxx, 16):
        for gy in np.arange(miny, maxy, 16):
            k = h32("p", int(gx), int(gy))
            x, y = gx + (k % 9 - 4), gy + ((k // 9) % 9 - 4)
            pt = Point(x, y)
            if pp.contains(pt) and not bp.contains(pt) and k % 10 < 6:   # ~60% fill
                xm, zm = x - X0, -(y - Y0)
                kind = [("broadleaf", 7, 10, (70, 108, 54)), ("conifer", 5, 13, (44, 82, 50)),
                        ("plane", 9, 13, (86, 120, 60))][k % 3]
                tshards[f"cell_{int(xm // 1000)}_{int(-zm // 1000)}"] += tree_prims(xm, zm, kind, k)
                n_park += 1
for cell, items in tshards.items():
    (OUT / "trees" / f"{cell}.json").write_text(json.dumps(items, separators=(",", ":"), allow_nan=False))

man = json.loads((PROC / "roblox" / "manifest.json").read_text())
man["styled"] = dict(
    buildings=sorted(f"styled/buildings/{p.name}" for p in (OUT / "buildings").glob("*.json")),
    roads=sorted(f"styled/roads/{p.name}" for p in (OUT / "roads").glob("*.json")),
    trees=sorted(f"styled/trees/{p.name}" for p in (OUT / "trees").glob("*.json")),
    looks={k: dict(base=v[0], texture=v[1], tile_m=v[2]) for k, v in LOOKS.items()},
    markings={"2": "road_2lane", "4": "road_4lane"}, decals={"foliage": "foliage"})
(PROC / "roblox" / "manifest.json").write_text(json.dumps(man, indent=1))

nb = sum(len(e["p"]) for v in bshards.values() for e in v)
nr = sum(len(e["p"]) for v in rshards.values() for e in v)
nt = sum(len(v) for v in tshards.values())
print(f"buildings {len(recs)} -> {nb} prims; archetypes {dict(arch_count)}")
print(f"roads -> {nr} prims ({n_side} sidewalk strips); trees: {n_tree} street + {n_park} park -> {nt} prims")
print(f"total prims {nb + nr + nt}")
