"""Shared constants for the Oakland Flood Consequence Explorer pipeline. Single source of truth."""
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
HAZ = PROC / "hazard"
for _d in (RAW, PROC, HAZ):
    _d.mkdir(parents=True, exist_ok=True)

USER_AGENT = "datafest-flood-pipeline/0.1"

# ------------------------------------------------------------------ geography
# Study area (EPSG:4326): West Oakland, Jack London Square, Port shoreline.
BBOX = dict(west=-122.335, south=37.790, east=-122.255, north=37.830)
# Wider area for the emergency-access network, so routes to facilities just outside the
# study area (e.g. Children's Hospital Oakland, north of the bbox) are found.
NETWORK_BBOX = dict(west=-122.345, south=37.770, east=-122.225, north=37.855)

CRS_GEO = "EPSG:4326"
CRS_METRIC = "EPSG:26910"  # NAD83 / UTM 10N, meters


def _grid_bounds():
    from pyproj import Transformer
    tf = Transformer.from_crs(CRS_GEO, CRS_METRIC, always_xy=True)
    pts = [tf.transform(x, y) for x in (BBOX["west"], BBOX["east"]) for y in (BBOX["south"], BBOX["north"])]
    xs, ys = zip(*pts)
    return (math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys)))


# The 1 m analysis grid (= DEM grid) in EPSG:26910: (left, bottom, right, top).
GRID_BOUNDS = _grid_bounds()
GRID_RES_M = 1.0

# ------------------------------------------------------------------ water levels
# Vertical datum: NAVD88 meters everywhere.
# NOAA CO-OPS 9414750 (Alameda), epoch 1983-2001, accessed 2026-11-21:
#   MHHW = 3.027 m STND, NAVD88 = 1.086 m STND  ->  MHHW = 1.941 m NAVD88.
NOAA_STATION = "9414750"
MHHW_NAVD88_M = 3.027 - 1.086
FT_TO_M = 0.3048

# Main scenarios: sea-level rise above MHHW, in feet.
SCENARIOS_FT = [0, 1, 2, 3, 4, 5]
SCENARIO_IDS = [f"{ft}ft" for ft in SCENARIOS_FT]


def water_level_m(ft):
    return MHHW_NAVD88_M + ft * FT_TO_M


# ART Bay Shoreline Flood Explorer water levels (inches above MHHW) used per scenario.
# ART publishes 0, 12, 24, 36, 48, 52, 66, 77, 84, 96, 108 in. There is NO 60 in level.
# Team decision (2026-11-21): the "5 ft" scenario uses ART 66 in (5.5 ft), the conservative
# choice; it is labeled as such everywhere. Set 5: None to use our bathtub model at 60 in.
ART_LEVEL_FOR_FT = {0: 0, 1: 12, 2: 24, 3: 36, 4: 48, 5: 66}
ART_BRACKET_LEVELS_IN = [52, 66]
IN_TO_M = 0.0254
ART_WMS = "https://mapserver.adaptingtorisingtides.org/cgi-bin/mapserv?map=/opt/slrviewer/mapfiles/bcdc.map"

# 1% annual-chance (100-year) still-water extreme at Alameda, above MHHW (NOAA CO-OPS
# Extreme Water Levels, GEV, accessed 2026-11-21): 0.84 m (90% CI 0.77-0.96).
# Used only for the supplementary bathtub storm runs.
SURGE_100YR_M = 0.84

# DEM vertical accuracy: CA_AlamedaCounty_2021 QL1, 10 cm RMSEz class,
# NVA <= 0.196 m at 95% (vendor metadata). Used as a +/- uniform-bias envelope.
DEM_NVA95_M = 0.196

ROAD_IMPASSABLE_DEPTH_M = 0.15

# Seed points for the bathtub flood fill, all in open water (lon, lat); verified on the DEM.
SEED_POINTS = {
    "open_bay_west_of_port": (-122.33204, 37.80509),
    "outer_harbor": (-122.32282, 37.81946),
    "inner_harbor_estuary": (-122.30944, 37.79279),
    "estuary_mid_jack_london": (-122.28901, 37.79132),
}

# ------------------------------------------------------------------ consequences
# OSM tags for critical facilities -> our facility type.
FACILITY_TAGS = {
    "amenity": {"school": "school", "kindergarten": "school", "college": "school",
                "hospital": "hospital", "clinic": "clinic", "doctors": "clinic",
                "fire_station": "fire_station", "police": "police",
                "social_facility": "shelter", "shelter": "shelter",
                "community_centre": "community_center"},
    "emergency": {"assembly_point": "shelter"},
    "railway": {"station": "rail_station"},
    "public_transport": {"station": "rail_station"},
    "highway": {"bus_stop": "bus_stop"},
}
CONTAMINATION_BUFFER_M = 100
DEGRADED_FACTOR = 2.0  # "degraded" access = travel time more than doubles ...
DEGRADED_MIN_EXTRA_S = 60  # ... AND grows by at least 1 minute (drive times here are short,
                           # so doubling 30 s -> 60 s alone isn't a meaningful loss)

# ------------------------------------------------------------------ equity priority
HIGH_BURDEN_PCTL = 75  # CalEnviroScreen 4.0 statewide percentile, top quartile
# Exposure = weighted mean of 0-1 normalized components (weights sum to 1).
# Emergency access loss share = (residents cut off + DEGRADED_ACCESS_WEIGHT x residents whose
# response time more than doubles) / tract residents. A lost fire station or clinic counts
# through the residents it served, not as a count in its own tract (Fire Station 2 sits in a
# tract with few residents). Cut off and degraded are one component, so a handful of degraded
# residents can't be stretched to a full component by the per-scenario max normalization.
DEGRADED_ACCESS_WEIGHT = 0.5  # ASSUMPTION: a doubled response time counts half as much as none
PRIORITY_WEIGHTS = {"flooded_building_share": 0.5, "emergency_access_loss_share": 0.5}
TOP_N_PRIORITY = 5

# ------------------------------------------------------------------ FloodWatch link (K1+)
# H3 resolution used by oakland-flood-vulnerability/ (FloodWatch): res 9, ~0.1 km2 hexes.
FLOODWATCH_H3_RES = 9
