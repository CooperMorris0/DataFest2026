"""Optional: OSM drivable network (wider NETWORK_BBOX) and OSM critical facilities.

The public Overpass API refused automated requests on 2026-11-21 (overpass-api.de connection
refused; other instances 403/502 with "browser use only" notices). This step is therefore
best-effort: if it can't download, the pipeline uses the study-bbox road network from
01_fetch_osm.py and authoritative facility datasets (01d_fetch_facilities.py) instead.
"""
import sys

import geopandas as gpd
import osmnx as ox
import pandas as pd

from config import CRS_GEO, CRS_METRIC, FACILITY_TAGS, NETWORK_BBOX, RAW, USER_AGENT

ox.settings.use_cache = True
ox.settings.cache_folder = str(RAW / "osm_cache")
ox.settings.http_user_agent = USER_AGENT
ox.settings.log_console = False
ox.settings.requests_timeout = 60


def keep(gdf, cols):
    cols = [c for c in cols if c in gdf.columns]
    return gdf[cols + ["geometry"]].copy()


def stringify(gdf):
    for c in gdf.columns:
        if c != "geometry" and gdf[c].dtype == object:
            gdf[c] = gdf[c].apply(lambda v: ";".join(map(str, v)) if isinstance(v, list) else v)
    return gdf


try:
    # ---- drivable network for the emergency-access analysis (wider area than the study bbox)
    out = RAW / "osm_drive_network.graphml"
    if not out.exists():
        nb = (NETWORK_BBOX["west"], NETWORK_BBOX["south"], NETWORK_BBOX["east"], NETWORK_BBOX["north"])
        G = ox.graph_from_bbox(nb, network_type="drive", simplify=True, truncate_by_edge=True)
        G = ox.add_edge_speeds(G)          # km/h from maxspeed, else per-highway-type means
        G = ox.add_edge_travel_times(G)    # seconds
        ox.save_graphml(G, out)
    G = ox.load_graphml(out)
    print(f"network: {len(G.nodes)} nodes, {len(G.edges)} edges")

    # ---- critical facilities (points; polygons -> representative point), wider network area
    out = RAW / "osm_facilities.geojson"
    if not out.exists():
        nb = (NETWORK_BBOX["west"], NETWORK_BBOX["south"], NETWORK_BBOX["east"], NETWORK_BBOX["north"])
        tags = {k: list(v) for k, v in FACILITY_TAGS.items()}
        f = ox.features_from_bbox(nb, tags=tags).reset_index()
        f["ftype"] = None
        for key, mapping in FACILITY_TAGS.items():  # first matching tag wins, in config order
            if key in f.columns:
                m = f["ftype"].isna() & f[key].isin(mapping)
                f.loc[m, "ftype"] = f.loc[m, key].map(mapping)
        f = f[f["ftype"].notna()].copy()
        # rail stations: keep passenger stations (BART + Amtrak), drop freight/yard nodes
        rail = f["ftype"] == "rail_station"
        if "station" in f.columns:
            f = f[~rail | f.get("station", pd.Series(index=f.index)).isin(["subway", "light_rail", "train"])
                  | f.get("network", pd.Series(index=f.index)).fillna("").str.contains("BART|Amtrak")
                  | f.get("operator", pd.Series(index=f.index)).fillna("").str.contains("BART|Amtrak")]
        # social_facility: keep shelters only (not e.g. outreach offices)
        if "social_facility" in f.columns:
            sf = f["amenity"].eq("social_facility")
            f = f[~sf | f["social_facility"].fillna("").str.contains("shelter")]
        f["geometry"] = f.geometry.to_crs(CRS_METRIC).representative_point().to_crs(CRS_GEO)
        f["fid"] = f["element"].astype(str) + "/" + f["id"].astype(str)
        f = f.drop_duplicates("fid")
        f = keep(f, ["fid", "ftype", "name", "amenity", "emergency", "healthcare", "network", "operator"])
        stringify(f).to_file(out, driver="GeoJSON")
    f = gpd.read_file(out)
    print("facilities:", f["ftype"].value_counts().to_dict())
except Exception as e:  # network down / Overpass refusing: degrade gracefully
    print(f"SKIPPED (Overpass unavailable): {type(e).__name__}: {str(e)[:200]}")
    sys.exit(0)
