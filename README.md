# Oakland Flood Consequence Explorer

DataFest 2026. A walkable 3D Roblox model of West Oakland and the waterfront that shows what sea-level rise *means for people*: who floods, who gets cut off from emergency services, which flooded areas are near contaminated sites, and which neighborhoods should be prioritized. It is built on official flood maps and open data.

> Official flood maps show where water goes. We show what it means for the people who live there, and where help should start.

**Status:** the data pipeline is complete and validated (definition of done #1), and the isolation, equity-priority and contamination analyses are working. The Roblox viewer is next: its data files are already exported to `data/processed/roblox/`. The planner brief is in [`brief/findings_brief.md`](brief/findings_brief.md).

This is an exploration tool, **not an official hazard or evacuation map**. Defer to ART, BCDC, and City of Oakland plans.

## Results (study area: 13,581 buildings, ~82,000 residents, 365 km of drivable road)

| Sea-level rise | Hazard source | Buildings flooded | Residents affected | Facilities lost | Residents cut off | Residents degraded access | Contaminated sites ≤100 m of flooding | Impassable road |
|---|---|---|---|---|---|---|---|---|
| 0 ft | ART | 0 | 0 | 0 | 0 | 0 | 0 | 0 km |
| +1 ft | ART 12 in | 6 | 8 | 0 | 0 | 0 | 17 | 0 km |
| +2 ft | ART 24 in | 14 | 8 | 0 | 0 | 0 | 17 | 0 km |
| +3 ft | ART 36 in | 49 | 907 | 0 | 71 | 0 | 23 | 2.9 km |
| +4 ft | ART 48 in | 117 | 1,341 | 1 (Fire Station 2) | 217 | 235 | 30 | 4.7 km |
| +5 ft | bathtub model* | 417 | 3,796 | 2 | 1,999 | 1,123 | 62 | 21.6 km |

\*ART has no 60-inch layer. ART's own maps flood 620 buildings at 52 in (4.3 ft) and 1,137 at 66 in (5.5 ft), so our +5 ft row is likely an **underestimate** relative to ART. To use an ART level instead, change `ART_LEVEL_FOR_FT[5]` in `pipeline/config.py`.

- **Equity:** at +3 and +4 ft, 96% and 94% of affected residents live in CalEnviroScreen top-quartile tracts, against 28% of all Oakland residents (3.4× over-represented). At +5 ft the share is 51%. Within the study area itself, 62% of residents are in such tracts. These are ecological, tract-level comparisons.
- **Emergency access:** Oakland Fire Station 2 (Jack London waterfront) floods from +4 ft, which more than doubles response times for 235 residents. At +5 ft, 1,999 residents are cut off from fire or medical services.
- **Hidden risk:** at +4 ft, 422 more buildings sit below the water level but behind higher ground (ART "low-lying" areas). Groundwater rise and drainage failure are not modeled.
- **Top priority tracts (+4 ft):** 4033.02 (Oakland, CalEnviroScreen 83rd percentile), 4287 (Alameda, 78), 9832 (Oakland, 55), 4017 (Oakland, 80), 4060 (Oakland, 88). The full ranking per scenario is in `stats.json` → `top_priority`, and the tract table is in `tract_table.csv`.

## Method

**Hazard (02, 05).** Flood extents come from the **ART Bay Shoreline Flood Explorer** (BCDC), read from its official MapServer (`mapserver.adaptingtorisingtides.org`, WMS layers `inundation<N>` / `lowlying<N>`). Each layer is rendered onto our 1 m grid. ART's WMS doesn't expose depth values, so **depth is estimated** inside ART's extent as water level minus 2021 USGS LiDAR ground, with a 1 cm floor so ART's extent is kept. Water level is MHHW 1.941 m NAVD88 (NOAA 9414750, Alameda) plus the scenario. For +5 ft, which ART doesn't publish, a **connected bathtub model** on the same LiDAR is used (`hazard_bathtub.py`): 4-connected flood fill from verified open-water seeds, with the sea mask cut from the OSM coastline and Lake Merritt treated as inland water.

**Exposure (05).**
- Building: flooded if any 1 m cell under the footprint floods.
- Road: impassable above 0.15 m depth. Bridges and tunnels are excluded.
- Facility: flooded if its building or its own cell floods.

**Consequences (06).**
- *Facilities:* schools, hospitals, clinics, nursing facilities, fire stations and BART stations in flooded areas.
- *Isolation:* the drivable network is the OSM study-area graph (directed) plus a ring of Census TIGER roads, stitched at the boundary, so routes reach Children's Hospital and Highland. Flooded edges and flooded facilities are removed.
  - Fire: response time *from* the nearest station.
  - Medical: travel time *to* the nearest hospital or clinic.
  - **Cut off** = no path. **Degraded** = more than 2× the baseline time *and* at least 1 minute longer.
- *Contamination:* open or managed-in-place EnviroStor and GeoTracker sites in or within 100 m of flooding.

**Equity and priority (07).** Tract population (2020 Census) is allocated to residential parcels (MTC/SFEI land use) by footprint area × height. Priority = Exposure × Vulnerability:
- Exposure is the mean of three components, each normalized 0–1 across tracts: share of buildings flooded, facilities lost, and share of residents cut off. The weights are in `PRIORITY_WEIGHTS`.
- Vulnerability is the CalEnviroScreen 4.0 percentile ÷ 100.

## Validation

| Check | 1 ft | 2 ft | 3 ft | 4 ft | 5 ft |
|---|---|---|---|---|---|
| ART vs our bathtub (IoU, land) | 0.74 | 0.80 | 0.68 | 0.73 | n/a |
| ART vs NOAA SLR Viewer (IoU) | 0.62 | 0.68 | NOAA n/a† | 0.73 | n/a |
| Bathtub vs NOAA (IoU) | 0.64 | 0.67 | NOAA n/a† | 0.86 | 0.88 |
| Buildings flooded: ART / bathtub | 6 / 7 | 14 / 9 | 49 / 46 | 117 / 109 | n/a / 417 |

†NOAA's `slr_3ft` service returns a blank render for this area (checked 2026-11-21).
- A Port strip that NOAA treats as disconnected connects in our model through a single 1 m cell at an at-grade intersection, at +4.73 ft (`port_discrepancy_sill.png`). That's a threshold effect, not a missing seawall.
- The bathtub's ±0.196 m DEM-accuracy runs give 150–1,200 flooded buildings at 5 ft. West Oakland is flat around 3.4–3.7 m, so counts near that level are very sensitive.

## Limitations and assumptions

- Exploration tool, not an official hazard or evacuation map. Still-water flooding only: no storm surge, rainfall, groundwater rise, or compound events. A 100-year storm tide adds ~0.84 m; supplementary bathtub runs are in `hazard/bathtub_summary.json`.
- **Depth is estimated** (ART extent combined with LiDAR). +5 ft uses our model, not ART.
- **Residents per building** is an area-based estimate. **97% of building heights are estimated** (OSM rarely tags height here). Roblox buildings are boxes.
- Drive times are free-flow estimates by road class, with no traffic, signals or dispatch time. TIGER ring roads are treated as two-way. Fire stations are Oakland's only, so Alameda and Emeryville stations are missing; the bbox includes part of Alameda.
- Contaminated-site proximity **does not mean residents are exposed**.
- CalEnviroScreen 4.0 uses 2010 tracts and population uses 2020 tracts; they are joined per building.
- **Priority sensitivity:** with equal weights, one lost facility in a tract carries a full third of the exposure score. At +5 ft this ranks a tract with zero affected residents #2. Adjust `PRIORITY_WEIGHTS` if that's not the intended emphasis.
- Overpass (the OSM API) refused automated requests during the build, so facilities come from authoritative agency datasets and the outer road ring comes from TIGER.

## Data sources (all accessed 2026-11-21)

| Data | Source |
|---|---|
| Flood hazard | ART Bay Shoreline Flood Explorer, SF Bay Conservation and Development Commission (WMS `mapserver.adaptingtorisingtides.org`, layers `inundation0/12/24/36/48/52/66`, `lowlying*`) |
| Elevation | USGS 3DEP 1 m DEM, project CA_AlamedaCounty_2021_B21 (QL1, 10 cm RMSEz class) |
| Tide datum | NOAA CO-OPS 9414750 Alameda datums; Extreme Water Levels product |
| Validation | NOAA Office for Coastal Management Sea Level Rise Viewer (`coast.noaa.gov/arcgis/rest/services/dc_slr`) |
| Buildings, study-area roads, coastline | OpenStreetMap via OSMnx, © OpenStreetMap contributors (ODbL) |
| Outer road ring | U.S. Census Bureau TIGER/Line 2025 roads, Alameda County |
| Land use (residential parcels) | MTC / SFEI Existing Land Use 2020 |
| Fire stations | City of Oakland GIS, OFD_Basemap |
| Hospitals, clinics, nursing facilities | CDPH Licensed and Certified Healthcare Facilities (CalHHS) |
| Schools | California Department of Education, California Public Schools 2024-25 |
| BART stations | City of Oakland GIS, Bart_Stations |
| Contaminated sites | DTSC EnviroStor (`Envirostor_Public_Data_Export`); SWRCB GeoTracker (`geotracker_sites_download`) |
| Equity | CalEnviroScreen 4.0 (OEHHA); 2020 Census tracts and places (TIGERweb) |
| Alignment check | Esri World Imagery |

## How to run

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
pipeline/run_all.sh
```

All downloads are cached in `data/raw/`. After the first run, a full rerun takes about 4 minutes.

| Step | Script | Key outputs (`data/processed/`) |
|---|---|---|
| 1 | `01_fetch_osm`, `01b_fetch_landuse`, `01c_fetch_network_osm` (optional), `01d_fetch_facilities`, `01e_fetch_tiger_roads`, `01f_fetch_contamination` | `data/raw/*` |
| 2 | `02_fetch_hazard` | `hazard/art_<N>in.tif` |
| 3 | `03_fetch_elevation` | `data/raw/dem_1m_navd88.tif` |
| 4 | `04_building_heights`, `04b_alignment_check` | `buildings.geojson`, `alignment_check.png` |
| fallback | `hazard_bathtub` | `hazard/bathtub_*.tif`, `sea_mask.png` |
| 5 | `05_flood_exposure`, `05b_validate_hazard` | `flood_<ft>ft.png`, `exposure_summary.json`, `hazard_validation.json` |
| 6 | `06_consequences` | `consequences_summary.json`, `contaminated_sites_flagged.geojson` |
| 7 | `07_equity_priority` | `tract_table.csv`, `equity_priority.json` |
| 8 | `08_export_for_roblox` | `roblox/` (heightmap, sharded buildings and roads, points, manifest), **`stats.json`** |
| 9 | `09_findings_brief` | `brief/findings_brief.md` |

Shared constants (bbox, datum, scenarios, ART levels, rules, weights, scale) are in `pipeline/config.py`.
