"""Consequence analyses per scenario.

A. Critical facilities: which schools, hospitals, clinics, nursing facilities, fire stations,
   and rail stations inside the study area are in flooded areas (names + counts).
B. Isolation (emergency access): drivable network = OSM study-area graph (directed) + a ring
   of Census TIGER roads outside it (undirected), stitched at the boundary. Edges flooded
   deeper than 0.15 m are removed; flooded facilities are unavailable.
     fire:     response time FROM nearest available fire station TO each building
     medical:  travel time FROM each building TO nearest available hospital or clinic
     hospital: same, acute-care hospitals only (reported, not used in the priority score)
   cut_off  = no path in the scenario (but a path at baseline)
   degraded = travel time > DEGRADED_FACTOR x baseline AND at least DEGRADED_MIN_EXTRA_S longer
C. Contamination proximity: open / managed-in-place EnviroStor + GeoTracker sites inside or
   within CONTAMINATION_BUFFER_M of flooded areas. PROXIMITY, NOT EXPOSURE.
   Buildings within the buffer of a flagged site are marked (residents counted in 07).

Speeds (no maxspeed data in our cached OSM extract) are typical urban values per road
class, a documented assumption. Outputs: buildings_consequences.parquet-like GeoJSON,
facilities_consequences.geojson, contaminated_sites_flagged.geojson,
network_edges.geojson (for Roblox / maps), consequences_summary.json
"""
import json

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely import STRtree
from shapely.geometry import box
from shapely.ops import unary_union

from common import point_rowcol, read
from config import (CONTAMINATION_BUFFER_M, CRS_METRIC, DEGRADED_FACTOR, DEGRADED_MIN_EXTRA_S, GRID_BOUNDS, PROC,
                    RAW, ROAD_IMPASSABLE_DEPTH_M, SCENARIO_IDS)

OSM_KMH = {"motorway": 88, "trunk": 72, "primary": 56, "secondary": 48, "tertiary": 40,
           "unclassified": 40, "residential": 40, "living_street": 16, "service": 24, "road": 32}
TIGER_KMH = {"S1100": 88, "S1200": 56, "S1400": 40, "S1630": 48, "S1640": 24, "S1730": 16}
STITCH_SEARCH_M = 40
CONNECTOR_KMH = 24

frame = box(*GRID_BOUNDS)
b = gpd.read_file(PROC / "buildings_exposure.geojson").to_crs(CRS_METRIC)
roads = gpd.read_file(PROC / "roads_exposure.geojson").to_crs(CRS_METRIC)
fac = gpd.read_file(PROC / "facilities_exposure.geojson").to_crs(CRS_METRIC)

# ============================================================ A. facilities
summary = {"facilities": {}, "isolation": {}, "contamination": {}}
in_area = fac[fac["in_study_area"]]
for sid in SCENARIO_IDS:
    hit = in_area[in_area[f"flooded_{sid}"]]
    summary["facilities"][sid] = dict(
        count=int(len(hit)), by_type=hit["ftype"].value_counts().to_dict(),
        list=[dict(name=n, type=t) for n, t in zip(hit["name"], hit["ftype"])])
    print(f"A {sid}: {len(hit)} facilities flooded {hit['ftype'].value_counts().to_dict()}")

# ============================================================ B. network
G = nx.MultiDiGraph()
osm = gpd.read_file(RAW / "osm_roads.geojson").to_crs(CRS_METRIC)  # directed edges (both ways if two-way)
flood_by_key = {}
roads["ukey"] = [tuple(sorted((u, v))) + (k,) for u, v, k in zip(roads.u, roads.v, roads.key)]
for sid in SCENARIO_IDS:
    flood_by_key[sid] = dict(zip(roads["ukey"], roads[f"impassable_{sid}"]))


def hw(v):
    v = str(v).split(";")[0]
    return v.replace("_link", "")


for r in osm.itertuples():
    cls = hw(r.highway)
    kmh = OSM_KMH.get(cls, 32)
    if str(r.highway).endswith("_link"):
        kmh = min(kmh, 48)
    coords = list(r.geometry.coords)
    for n, xy in ((r.u, coords[0]), (r.v, coords[-1])):
        if n not in G:
            G.add_node(n, x=xy[0], y=xy[1], src="osm", freeway=False)
        if cls in ("motorway", "trunk"):
            G.nodes[n]["freeway"] = True
    uk = tuple(sorted((r.u, r.v))) + (r.key,)
    G.add_edge(r.u, r.v, key=f"osm{r.key}", length=r.geometry.length,
               travel_time=r.geometry.length / (kmh / 3.6), src="osm", ukey=uk,
               **{f"imp_{sid}": bool(flood_by_key[sid].get(uk, False)) for sid in SCENARIO_IDS})
n_osm_nodes = G.number_of_nodes()

# TIGER ring: edges whose midpoint lies outside the study frame
tg = gpd.read_file(RAW / "tiger_roads_06001.geojson").to_crs(CRS_METRIC)
tg = tg[tg["MTFCC"].isin(TIGER_KMH)].explode(index_parts=False).reset_index(drop=True)
# TIGER road features span many intersections: split ("node") them where they cross.
# Freeways (S1100) are noded only among themselves so overpasses don't become junctions;
# they connect to ramps/streets only where endpoints coincide (rounded to 0.5 m below).
pieces = []
for grp in (tg[tg.MTFCC != "S1100"], tg[tg.MTFCC == "S1100"]):
    if not len(grp):
        continue
    merged = unary_union(list(grp.geometry))
    parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    srcs = STRtree(list(grp.geometry))
    for p in parts:
        mid = p.interpolate(0.5, normalized=True)
        k = srcs.nearest(mid)
        pieces.append(dict(MTFCC=grp.MTFCC.iat[k], geometry=p))
tg = gpd.GeoDataFrame(pieces, crs=CRS_METRIC)
tg = tg[~tg.geometry.interpolate(0.5, normalized=True).within(frame)]
tnode = {}


def tiger_node(xy, fw):
    k = (round(xy[0] * 2) / 2, round(xy[1] * 2) / 2)
    if k not in tnode:
        nid = f"t{len(tnode)}"
        tnode[k] = nid
        G.add_node(nid, x=k[0], y=k[1], src="tiger", freeway=fw)
    elif fw:
        G.nodes[tnode[k]]["freeway"] = True
    return tnode[k]


for r in tg.itertuples():
    kmh = TIGER_KMH[r.MTFCC]
    fw = r.MTFCC == "S1100"
    cs = list(r.geometry.coords)
    a, c = tiger_node(cs[0], fw), tiger_node(cs[-1], fw)
    if a == c:
        continue
    L = r.geometry.length
    for x, y in ((a, c), (c, a)):  # TIGER has no one-way info: treat as two-way
        G.add_edge(x, y, key="tiger", length=L, travel_time=L / (kmh / 3.6), src="tiger",
                   **{f"imp_{sid}": False for sid in SCENARIO_IDS})

# stitch OSM boundary nodes to nearby TIGER nodes of the same class (freeway vs surface)
osm_nodes = [n for n, d in G.nodes(data=True) if d["src"] == "osm"]
oxy = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in osm_nodes])
near_edge = np.array([frame.exterior.distance(gpd.points_from_xy([x], [y])[0]) < 250 for x, y in oxy])
tig_nodes = [n for n, d in G.nodes(data=True) if d["src"] == "tiger"]
txy = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in tig_nodes])
tree = cKDTree(txy)
stitched = 0
for (x, y), n, ok in zip(oxy, osm_nodes, near_edge):
    if not ok:
        continue
    for j in tree.query_ball_point([x, y], STITCH_SEARCH_M):
        t = tig_nodes[j]
        if G.nodes[t]["freeway"] != G.nodes[n]["freeway"]:
            continue
        d = float(np.hypot(*(txy[j] - [x, y])))
        for p, q in ((n, t), (t, n)):
            G.add_edge(p, q, key="stitch", length=d, travel_time=d / (CONNECTOR_KMH / 3.6) + 1,
                       src="stitch", **{f"imp_{sid}": False for sid in SCENARIO_IDS})
        stitched += 1
print(f"network: {n_osm_nodes} OSM nodes + {len(tnode)} TIGER ring nodes, {G.number_of_edges()} edges, "
      f"{stitched} stitches")
# keep the largest weakly connected component (drops stray fragments)
big = max(nx.weakly_connected_components(G), key=len)
G = G.subgraph(big).copy()
print(f"largest component: {G.number_of_nodes()} nodes")

nodes = list(G.nodes)
nxy = np.array([[G.nodes[n]["x"], G.nodes[n]["y"]] for n in nodes])
node_tree = cKDTree(nxy)
osm_idx = np.array([G.nodes[n]["src"] == "osm" for n in nodes])
osm_tree = cKDTree(nxy[osm_idx])
osm_list = [n for n, o in zip(nodes, osm_idx) if o]

# origins: residential buildings (all buildings get flags; residential used for residents)
cent = b.geometry.representative_point()
_, oi = osm_tree.query(np.c_[cent.x, cent.y])
b["node"] = [osm_list[i] for i in oi]

TARGETS = {"fire": fac["ftype"].eq("fire_station"),
           "medical": fac["ftype"].isin(["hospital", "clinic"]),
           "hospital": fac["ftype"].eq("hospital")}
_, fi = node_tree.query(np.c_[fac.geometry.x, fac.geometry.y])
fac["node"] = [nodes[i] for i in fi]


def travel_times(H, kind, sid):
    avail = TARGETS[kind] & ~fac[f"flooded_{sid}"] if sid else TARGETS[kind]
    srcs = set(fac.loc[avail, "node"]) & set(H.nodes)
    if not srcs:
        return {}
    # fire: from station outward (response). medical/hospital: from home to facility -> reverse graph
    graph = H if kind == "fire" else H.reverse(copy=False)
    return nx.multi_source_dijkstra_path_length(graph, srcs, weight="travel_time")


def scenario_graph(sid):
    H = G.copy()
    drop = [(u, v, k) for u, v, k, d in H.edges(keys=True, data=True) if d[f"imp_{sid}"]]
    H.remove_edges_from(drop)
    return H, len(drop)


base = {k: travel_times(G, k, None) for k in TARGETS}
for k in TARGETS:
    b[f"tt_{k}_base_s"] = b["node"].map(base[k]).astype(float).round(1)
unreachable0 = b[[f"tt_{k}_base_s" for k in ("fire", "medical")]].isna().any(axis=1)
print(f"buildings with no baseline route (network fragment): {int(unreachable0.sum())}")

for sid in SCENARIO_IDS:
    H, ndrop = scenario_graph(sid)
    res = {}
    for k in TARGETS:
        tt = travel_times(H, k, sid)
        t = b["node"].map(tt).astype(float)
        t0 = b[f"tt_{k}_base_s"]
        cut = t0.notna() & t.isna()
        deg = t0.notna() & t.notna() & (t > DEGRADED_FACTOR * t0) & (t - t0 >= DEGRADED_MIN_EXTRA_S)
        b[f"cut_off_{k}_{sid}"] = cut
        b[f"degraded_{k}_{sid}"] = deg
        b[f"tt_{k}_{sid}_s"] = t.round(1)
        res[k] = dict(cut_off=int(cut.sum()), degraded=int(deg.sum()))
    b[f"cut_off_{sid}"] = b[f"cut_off_fire_{sid}"] | b[f"cut_off_medical_{sid}"]
    b[f"degraded_{sid}"] = ~b[f"cut_off_{sid}"] & (b[f"degraded_fire_{sid}"] | b[f"degraded_medical_{sid}"])
    summary["isolation"][sid] = dict(edges_removed=ndrop, **res,
                                     buildings_cut_off=int(b[f"cut_off_{sid}"].sum()),
                                     buildings_degraded=int(b[f"degraded_{sid}"].sum()))
    print(f"B {sid}: removed {ndrop} edges; cut off {int(b[f'cut_off_{sid}'].sum())}, "
          f"degraded {int(b[f'degraded_{sid}'].sum())}  {res}")

# ============================================================ C. contamination
sites = gpd.read_file(RAW / "contaminated_sites.geojson").to_crs(CRS_METRIC)
# merge the same site listed in both databases: within 25 m -> keep the first (EnviroStor first)
sites = sites.sort_values("source").reset_index(drop=True)
st = cKDTree(np.c_[sites.geometry.x, sites.geometry.y])
dup = np.zeros(len(sites), bool)
for i, j in sorted(st.query_pairs(25)):
    if not dup[i] and sites.at[i, "source"].split()[0] != sites.at[j, "source"].split()[0]:
        dup[j] = True
sites = sites[~dup].reset_index(drop=True)
sr, sc, s_on = point_rowcol(sites.geometry.x, sites.geometry.y)
sites["in_study_area"] = s_on
print(f"contaminated sites: {len(sites)} after cross-database dedupe ({int(dup.sum())} merged), "
      f"{int(s_on.sum())} on the analysis grid")
bxy = np.c_[cent.x, cent.y]
btree = cKDTree(bxy)
for sid in SCENARIO_IDS:
    flooded = read(PROC / f"flood_depth_{sid}.tif") > 0
    if flooded.any():
        dist = ndimage.distance_transform_edt(~flooded)  # m to nearest flooded cell
        d = np.full(len(sites), np.inf)
        d[s_on] = dist[sr[s_on], sc[s_on]]
    else:
        d = np.full(len(sites), np.inf)
    sites[f"in_flood_{sid}"] = d == 0
    sites[f"near_flood_{sid}"] = d <= CONTAMINATION_BUFFER_M
    flagged = sites[sites[f"near_flood_{sid}"]]
    near_b = np.zeros(len(b), bool)
    if len(flagged):
        for lst in btree.query_ball_point(np.c_[flagged.geometry.x, flagged.geometry.y], CONTAMINATION_BUFFER_M):
            near_b[lst] = True
    b[f"near_contam_{sid}"] = near_b
    summary["contamination"][sid] = dict(
        sites_in_flood=int(sites[f"in_flood_{sid}"].sum()), sites_near_flood=int(len(flagged)),
        by_category=flagged["category"].value_counts().to_dict(),
        buildings_within_buffer=int(near_b.sum()))
    print(f"C {sid}: {int(sites[f'in_flood_{sid}'].sum())} sites in flood, {len(flagged)} within "
          f"{CONTAMINATION_BUFFER_M} m; buildings within buffer {int(near_b.sum())}")

# ============================================================ outputs
b.drop(columns=["node"]).to_file(PROC / "buildings_consequences.geojson", driver="GeoJSON")
fac.drop(columns=["node"]).to_file(PROC / "facilities_consequences.geojson", driver="GeoJSON")
sites.to_file(PROC / "contaminated_sites_flagged.geojson", driver="GeoJSON")
summary["network"] = dict(osm_nodes=n_osm_nodes, tiger_ring_nodes=len(tnode), stitches=stitched,
                          nodes=G.number_of_nodes(), edges=G.number_of_edges(),
                          speeds_kmh=dict(osm=OSM_KMH, tiger=TIGER_KMH),
                          buildings_without_baseline_route=int(unreachable0.sum()))
summary["routing_facilities"] = {k: int(v.sum()) for k, v in TARGETS.items()}
(PROC / "consequences_summary.json").write_text(json.dumps(summary, indent=1, default=str))
