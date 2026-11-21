"""Shared constants for the Oakland flood pipeline. Single source of truth."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROC.mkdir(parents=True, exist_ok=True)

# Study area (EPSG:4326): West Oakland, Jack London Square, Port shoreline.
BBOX = dict(west=-122.335, south=37.790, east=-122.255, north=37.830)

CRS_GEO = "EPSG:4326"
CRS_METRIC = "EPSG:26910"  # NAD83 / UTM 10N, meters

# Raster resolution used by the flood model (m). The source LiDAR DEM is 1 m.
DEM_RES_M = 1.0

# Vertical datum: everything in NAVD88 meters.
# NOAA CO-OPS station 9414750 (Alameda), epoch 1983-2001, accessed 2026-11-21:
#   MHHW = 3.027 m STND, NAVD88 = 1.086 m STND  ->  MHHW = 1.941 m NAVD88.
NOAA_STATION = "9414750"
MHHW_NAVD88_M = 3.027 - 1.086

FT_TO_M = 0.3048
SCENARIOS_FT = [0, 1, 2, 3, 5]
WATER_LEVELS_M = [MHHW_NAVD88_M + s * FT_TO_M for s in SCENARIOS_FT]

# 1% annual-chance (100-year) still-water extreme at Alameda 9414750, relative to MHHW.
# NOAA CO-OPS Extreme Water Levels (GEV, detrended), accessed 2026-11-21:
#   level 0.84 m, 90% CI 0.77-0.96 m. Stored in data/raw/noaa_ewl_9414750.json.
SURGE_100YR_M = 0.84

# Scenario ids. Still-water ids keep the "<ft>ft" form used in file names.
SCENARIOS = (
    [dict(id=f"{ft}ft", slr_ft=ft, storm=None, water_m=MHHW_NAVD88_M + ft * FT_TO_M)
     for ft in SCENARIOS_FT]
    + [dict(id=f"{ft}ft_100yr", slr_ft=ft, storm="100yr",
            water_m=MHHW_NAVD88_M + ft * FT_TO_M + SURGE_100YR_M) for ft in SCENARIOS_FT]
)

# DEM vertical accuracy: CA_AlamedaCounty_2021 QL1, 10 cm RMSEz class,
# NVA <= 0.196 m at 95% (vendor metadata). Used as a +/- uniform-bias envelope.
DEM_NVA95_M = 0.196

ROAD_IMPASSABLE_DEPTH_M = 0.15

# Seed points for the hydrologic flood fill, all well out in open water (lon, lat).
SEED_POINTS = {
    # verified against the DEM: each lands on hydro-flattened bay water (see sea_mask.png)
    "open_bay_west_of_port": (-122.33204, 37.80509),
    "outer_harbor": (-122.32282, 37.81946),
    "inner_harbor_estuary": (-122.30944, 37.79279),
    "estuary_mid_jack_london": (-122.28901, 37.79132),
}

# Roblox scale (kept here so Python and Luau share one value later).
STUDS_PER_METER = 1 / 0.28

USER_AGENT = "datafest-flood-pipeline/0.1"
