"""Fetch OSM buildings, roads, and water/coastline for the bbox. Cached in data/raw."""
import geopandas as gpd
import osmnx as ox
import pandas as pd

from config import BBOX, CRS_GEO, RAW, USER_AGENT

ox.settings.use_cache = True
ox.settings.cache_folder = str(RAW / "osm_cache")
ox.settings.http_user_agent = USER_AGENT
ox.settings.log_console = False

bbox = (BBOX["west"], BBOX["south"], BBOX["east"], BBOX["north"])  # osmnx 2.x order


def keep(gdf, cols):
    cols = [c for c in cols if c in gdf.columns]
    return gdf[cols + ["geometry"]].copy()


def stringify(gdf):
    for c in gdf.columns:
        if c != "geometry" and gdf[c].dtype == object:
            gdf[c] = gdf[c].apply(lambda v: ";".join(map(str, v)) if isinstance(v, list) else v)
    return gdf


out = RAW / "osm_buildings.geojson"
if not out.exists():
    b = ox.features_from_bbox(bbox, tags={"building": True, "building:part": True})
    b = b[b.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].reset_index()
    b["osm_id"] = b["element"].astype(str) + "/" + b["id"].astype(str)
    b = keep(b, ["osm_id", "building", "building:part", "building:levels", "height",
                 "min_height", "layer", "location", "amenity", "parking", "name"])
    stringify(b).to_crs(CRS_GEO).to_file(out, driver="GeoJSON")
print("buildings:", len(gpd.read_file(out)))

out = RAW / "osm_roads.geojson"
if not out.exists():
    G = ox.graph_from_bbox(bbox, network_type="drive", simplify=True, truncate_by_edge=True)
    e = ox.graph_to_gdfs(G, nodes=False).reset_index()
    e = keep(e, ["u", "v", "key", "osmid", "highway", "name", "lanes", "width",
                 "bridge", "tunnel", "layer", "length"])
    stringify(e).to_crs(CRS_GEO).to_file(out, driver="GeoJSON")
print("road edges:", len(gpd.read_file(out)))

out = RAW / "osm_water.geojson"
if not out.exists():
    w = ox.features_from_bbox(bbox, tags={"natural": ["coastline", "water", "bay"],
                                          "water": True, "landuse": ["harbour", "basin"]})
    w = w.reset_index()
    w = keep(w, ["element", "id", "natural", "water", "landuse", "name"])
    stringify(w).to_crs(CRS_GEO).to_file(out, driver="GeoJSON")
w = gpd.read_file(out)
print("water features:", len(w), w.geometry.geom_type.value_counts().to_dict())
