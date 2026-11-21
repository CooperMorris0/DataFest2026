# Oakland Sea-Level Rise & Flooding Simulator

DataFest 2026. Which buildings, roads, and communities in West Oakland, Jack London Square, and the Port of Oakland shoreline flood at **+1, 2, 3, and 5 ft** of sea-level rise, and who bears the risk?

**Status:** the data pipeline and flood model are working and validated against NOAA. The 3D Roblox viewer is next (see `oakland_flooding.md` for the plan).

## Headline results

Study area: bbox −122.335, 37.790 → −122.255, 37.830 (≈ 7.1 × 4.5 km). It contains 13,602 buildings, 365 km of drivable road, and ≈ 82,000 residents (estimated). Water levels are relative to today's Mean Higher High Water (MHHW).

| SLR | Water level (NAVD88) | Flooded land | Buildings flooded | in high-burden tracts | Residents affected (est.) | Impassable road |
|---|---|---|---|---|---|---|
| 0 ft (today's MHHW) | 1.94 m | 0.19 km² | 6 | 1 | ~6 | 0 km |
| +1 ft | 2.25 m | 0.31 km² | 7 | 1 | ~6 | 0.7 km |
| +2 ft | 2.55 m | 0.40 km² | 9 | 2 | ~28 | 1.0 km |
| +3 ft | 2.86 m | 0.88 km² | 46 | 28 | ~1,200 | 4.2 km |
| +5 ft | 3.47 m | 3.38 km² | 417 (357 Oakland, 60 Alameda) | 275 | ~4,170 | 22.6 km |

- **There's a threshold between 3 and 5 ft.** Up to 2 ft the waterfront mostly holds. At 3 ft the Jack London/Brooklyn Basin edge starts to go. At 5 ft water reaches inland south of West Oakland (around Howard Terminal and the Jack London district) and the I-80/Bay Bridge approach shoreline.
- **Equity, stated carefully:** most flooded buildings at 5 ft (66%) are in high-burden tracts (CalEnviroScreen 4.0 ≥ 75th percentile statewide). Tract 06001402200 in West Oakland (93rd percentile) has the most flooded buildings (127). However, 68% of *all* buildings in the study area are already in high-burden tracts, so within this bbox flooding is **not disproportionate** to the baseline. Affected residents are 49% high-burden, against a 61% baseline, because much of the flooding hits Port and industrial land and newer waterfront housing. The honest framing is that the communities exposed here are overwhelmingly ones that already carry the state's highest pollution burdens. A comparison against the wider region would be needed to claim disproportionality.
- Full per-tract numbers are in `data/processed/tract_table.csv`, and everything is in `data/processed/stats.json`.

## Method

Connected "bathtub" model on a 1 m LiDAR DEM:

1. **Water level:** $W_s = \text{MHHW}_{\text{NAVD88}} + \Delta_s$, with MHHW = **1.941 m NAVD88** from NOAA CO-OPS station **9414750 (Alameda)**, epoch 1983–2001 (MHHW 3.027 m − NAVD88 1.086 m above station datum). Alameda is closer to the study area than San Francisco (9414290, which would give 1.798 m).
2. **Sea mask:** OSM's "San Francisco Bay" polygon is too coarse because it misses the harbors and the estuary. The DEM extent is cut along OSM `natural=coastline` instead, and the pieces containing hand-verified seed points in open water are kept (open bay, Outer Harbor, Inner Harbor/estuary, estuary at Jack London). See `data/processed/sea_mask.png`.
3. **Flood fill:** a cell floods if $z < W_s$ **and** it is 4-connected to the sea (`scipy.ndimage.label`). 4-connectivity stops water leaking diagonally through 1-pixel seawalls. Low ground that isn't connected is reported separately as "low but disconnected" and is not counted as flooded. Lake Merritt and its channel are treated as inland water: they can convey flooding but are not counted as flooded land.
4. **Buildings:** flooded if any 1 m cell under the footprint has depth > 0. The script stores max depth, the wet fraction of the footprint, and base elevation (the lowest ground under the footprint).
5. **Roads:** each segment is sampled every 1 m. It is impassable if max depth > 0.15 m (6 in). Bridges, viaducts, and tunnels are excluded, because the bare-earth DEM doesn't represent their deck height.
6. **Equity:** each building is joined, by representative point, to a 2020 Census tract (population), a CalEnviroScreen 4.0 tract (score), and an incorporated place (city). Tract population inside the bbox (POP100 × land fraction inside the bbox) is allocated to residential-candidate buildings in proportion to footprint area × height.

## Validation against the NOAA Sea Level Rise Viewer

`04b_validate_noaa.py` exports NOAA's connected-inundation layer for our exact bbox and compares it with our flooded land cell by cell at 4 m:

| SLR | NOAA connected | Ours | IoU | Share of NOAA area we also flood |
|---|---|---|---|---|
| +1 ft | 0.17 km² | 0.22 km² | 0.64 | 91% |
| +2 ft | 0.29 km² | 0.31 km² | 0.67 | 84% |
| +3 ft | n/a | 0.76 km² | n/a | NOAA's `slr_3ft` service returns a blank all-"low-lying" image for this area (any projection or size, checked 2026-11-21); 4 ft renders fine |
| +5 ft | 3.07 km² | 3.38 km² | **0.88** | **98.5%** |

Main discrepancy: a strip of Port land near the Outer Harbor that we flood and NOAA classifies as low-lying but disconnected. A seawall or berm captured in NOAA's hydro-connectivity edits is probably missing from the bare-earth DEM. See `data/processed/noaa_compare_5ft.png`.

## Limitations and assumptions

- **No storm surge, waves, rainfall, groundwater rise, levee failure, or pump/tide-gate operation.** This is a still-water, permanent-inundation view. Real flood risk (for example a 100-year storm on top of +3 ft) is substantially worse.
- The bare-earth DEM may not capture seawalls, floodwalls, or bulkheads narrower than ~1 m, which can make our model flood areas that are actually protected (see the Port discrepancy above).
- The LiDAR is hydro-flattened over water; bay depths aren't real bathymetry. This doesn't affect the land flood results.
- **Building heights are 97% estimated** (92% use the 6 m default, because OSM rarely has `height` or `building:levels` here). Heights don't affect flood counts, only 3D massing and the population floor-area proxy.
- Residential vs. non-residential is inferred from OSM `building` tags. 87% are `building=yes`, which is treated as potentially residential. Resident counts are **estimates**.
- CalEnviroScreen 4.0 uses 2010 tract geography and population uses 2020 tracts. They're joined per building, not tract-to-tract.
- Houseboats (28) are excluded because they float. Also dropped: roofs/canopies (89), slivers < 8 m² (249), and duplicate or overlapping `building:part` polygons (446).
- The "phantom footprint by LiDAR height < 1 m" rule from the brief wasn't applied, because it needs a surface model (DSM) and only the bare-earth DEM was used.
- The bbox includes part of Alameda (60 flooded buildings at 5 ft) and a sliver of Emeryville. Totals are split by city in `stats.json` → `by_city`.

## Data sources (accessed 2026-11-21)

- **OpenStreetMap** via OSMnx 2.2: buildings, drivable roads, coastline and water. © OpenStreetMap contributors, ODbL.
- **USGS 3DEP 1 m DEM**, project `CA_AlamedaCounty_2021_B21`, tiles x55y419 and x56y419, found via the TNM Access API and read as windowed COG reads. NAD83 / UTM 10N, NAVD88 meters.
- **NOAA CO-OPS** tidal datums, station 9414750 (Alameda): `api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/9414750/datums.json`
- **NOAA Office for Coastal Management Sea Level Rise Viewer** map services (`coast.noaa.gov/arcgis/rest/services/dc_slr/slr_<N>ft`), used for validation only.
- **CalEnviroScreen 4.0** (CA OEHHA), from OEHHA's ArcGIS feature service `CalEnviroScreen_4_0_Results_`.
- **U.S. Census Bureau TIGERweb**, 2020 Census tracts (with POP100) and incorporated places.
- **Esri World Imagery** tiles, used for the alignment check image only.

## How to run

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
pipeline/run_all.sh
```

Scripts, run in order and all reading `pipeline/config.py` (bbox, datum, scenarios, seeds, scale):

| Script | Does | Key outputs (`data/processed/`) |
|---|---|---|
| `01_fetch_osm.py` | OSM buildings, roads, water | `data/raw/osm_*.geojson` |
| `02_fetch_elevation.py` | 3DEP 1 m DEM, merged and clipped | `data/raw/dem_1m_navd88.tif` |
| `03_building_heights.py` | clean, dedupe, heights | `buildings.geojson` |
| `03b_alignment_check.py` | OSM over hillshade and imagery | `alignment_check.png` |
| `04_flood_model.py` | sea mask, connected flood fill, building and road flags | `sea_mask.png`, `flood_<ft>ft.png`, `flood_depth_<ft>ft.tif`, `flood_model_summary.json` |
| `04b_validate_noaa.py` | comparison with NOAA SLR Viewer | `noaa_compare_<ft>ft.png`, `noaa_validation.json` |
| `05_equity_overlay.py` | tracts, CalEnviroScreen, population, cities | `buildings_final.geojson`, `roads_final.geojson`, `tract_table.csv`, **`stats.json`** |

Downloads are cached in `data/raw/` and are never re-fetched once present. The full run takes about 2 minutes after the first download.

## Next

The Roblox Studio viewer (`06_export_for_roblox.py` plus Luau modules), built from `buildings_final.geojson`, `roads_final.geojson`, the DEM, and `stats.json`, following the plan in `oakland_flooding.md`.
