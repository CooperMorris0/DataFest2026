# Oakland Flood Consequence Explorer

DataFest 2026. A walkable 3D Roblox model of West Oakland and the waterfront that shows what sea-level rise *means for people*: who floods, who gets cut off from emergency services, which flooded areas are near contaminated sites, and which neighborhoods should be prioritized. It is built on official flood maps and open data.

> Official flood maps show where water goes. We show what it means for the people who live there, and where help should start.

**Status (2026-11-21):** all six items in the definition of done exist.
- The pipeline is validated.
- The **3D Roblox world** is built: terrain, buildings, rising water, and five map modes (Flood, Cut off, Contamination, Priority, FloodWatch). It's walkable, with a water-depth readout, and saved in the team place.
- The planner brief is in [`brief/findings_brief.md`](brief/findings_brief.md), and a presenter's walkthrough is in [`docs/demo_script.md`](docs/demo_script.md).
- Still open: a visual playtest, screenshots for the brief, and teammates' follow-up tasks (see "Team").

This is an exploration tool, **not an official hazard or evacuation map**. Defer to ART, BCDC, and City of Oakland plans.

## Results (study area: 13,581 buildings, ~82,000 residents, 365 km of drivable road)

| Sea-level rise | Hazard source | Buildings flooded | Residents affected | Facilities lost | Residents cut off | Residents degraded access | Contaminated sites ≤100 m of flooding | Impassable road |
|---|---|---|---|---|---|---|---|---|
| 0 ft | ART | 0 | 0 | 0 | 0 | 0 | 0 | 0 km |
| +1 ft | ART 12 in | 6 | 8 | 0 | 0 | 0 | 17 | 0 km |
| +2 ft | ART 24 in | 14 | 8 | 0 | 0 | 0 | 17 | 0 km |
| +3 ft | ART 36 in | 49 | 907 | 0 | 71 | 0 | 23 | 2.9 km |
| +4 ft | ART 48 in | 117 | 1,341 | 1 (Fire Station 2) | 217 | 235 | 30 | 4.7 km |
| +5 ft | ART 66 in* | 1,137 | 7,689 | 2 | 5,536 | 41 | 110 | 46.7 km |

\*ART has no 60-inch layer. By team decision (2026-11-21), the "+5 ft" scenario uses ART's **66-inch (5.5 ft)** map, a deliberately conservative choice; it is labeled as ART 66 in everywhere. For reference, ART 52 in (4.3 ft) floods 620 buildings and our LiDAR bathtub model at exactly 5 ft floods 417. Set `ART_LEVEL_FOR_FT[5] = None` in `pipeline/config.py` to use the bathtub model instead. Degraded access is low at +5 ft because most affected residents are fully cut off.

- **Equity:** at +3 and +4 ft, 96% and 94% of affected residents live in CalEnviroScreen top-quartile tracts, against 28% of all Oakland residents (3.4× over-represented). At +5 ft (ART 66 in) the share is 93%. Within the study area itself, 62% of residents are in such tracts. These are ecological, tract-level comparisons.
- **Emergency access:** Oakland Fire Station 2 (Jack London waterfront) floods from +4 ft, which more than doubles response times for 235 residents. At +5 ft (ART 66 in), 5,536 residents are cut off from fire or medical services.
- **Hidden risk:** at +4 ft, 422 more buildings sit below the water level but behind higher ground (ART "low-lying" areas). Groundwater rise and drainage failure are not modeled.
- **Top priority tracts (+4 ft):** 4033.02 (Oakland, CalEnviroScreen 83rd percentile), 4287 (Alameda, 78), 9832 (Oakland, 55), 4017 (Oakland, 80), 4060 (Oakland, 88). The full ranking per scenario is in `stats.json` → `top_priority`, and the tract table is in `tract_table.csv`.

### Flooding today vs. flooding tomorrow (with Kai's FloodWatch)

[FloodWatch](oakland-flood-vulnerability/) (Kai) maps where Oakland *already* floods when it rains, using about 6,200 OAK 311 flood reports, an ML model, FEMA zones and CDC SVI. Inside our study area it covers 289 H3 blocks with **1,521 flood reports since 2013** (19 Very high and 72 High risk blocks).
- **They are mostly different places.** Only 47 blocks have both 311 rain flooding and sea-level flooding at +5 ft. Only 17 of the 91 High / Very high rain-risk blocks flood at +5 ft, and just 25% of the reports (382 of 1,521) come from blocks that sea-level rise floods. (Kai's K1 found the same 47-block overlap.)
- So West Oakland faces **two different flood problems**: storm drains overwhelmed in the residential flatlands today, and permanent shoreline flooding at the waterfront later. Adaptation plans need both.

## 3D Roblox world

A walkable model of the study area (1 stud = 0.28 m) in the team's Roblox place "DataFest2026" (placeId 139477133252061). Setup and rebuild steps are in [`roblox/SETUP.md`](roblox/SETUP.md).
- **Scenario buttons** (Today to +5 ft) raise the bay. Each scenario's flood water appears only where the hazard data floods.
- **Map modes:**
  - **Flood:** depth on buildings; impassable roads in red.
  - **Cut off:** cut-off or degraded emergency access.
  - **Contamination:** cleanup sites near flooding.
  - **Priority:** equity-weighted tracts.
  - **FloodWatch:** Kai's website in 3D, with the same hexagons, risk colors, percentiles and 311 counts (289/289 blocks identical), plus columns sized by flood reports.
- **Stats panel and "where help should start" list** are read straight from `stats.json`, so the numbers always match this README.
- **Walk mode:** solid buildings; you're dropped onto the nearest street. An on-screen readout shows the street name, **how deep the water is at your feet** (ankle-, knee-, waist-deep) and the FloodWatch block you're in. Wading slows you down.
- **Fly camera and viewpoints:** Overview, West Oakland, Jack London, Port, Fire Station 2. Click a building for its depth, emergency access, height, tract and FloodWatch risk.
- **Deep link from the FloodWatch website:** `https://www.roblox.com/games/start?placeId=139477133252061&launchData=<h3>` opens the world walking in that block. Production use needs the experience to be published.
- **Verified in Studio:** the flooded and cut-off counts of building parts match `stats.json` for all 6 scenarios. Not yet verified by eye: overall visuals and button clicks. The MCP screenshot tool returned stale frames, so this needs a human playtest.

## Method

**Hazard (02, 05).** Flood extents come from the **ART Bay Shoreline Flood Explorer** (BCDC), read from its official MapServer (`mapserver.adaptingtorisingtides.org`, WMS layers `inundation<N>` / `lowlying<N>`). Each layer is rendered onto our 1 m grid. ART's WMS doesn't expose depth values, so **depth is estimated** inside ART's extent as water level minus 2021 USGS LiDAR ground, with a 1 cm floor so ART's extent is kept. Water level is MHHW 1.941 m NAVD88 (NOAA 9414750, Alameda) plus the scenario. ART has no 60-inch layer, so "+5 ft" uses ART 66 in, with depth estimated at the 66-inch water level. A **connected bathtub model** on the same LiDAR (`hazard_bathtub.py`) is the fallback and the cross-check: 4-connected flood fill from verified open-water seeds, with the sea mask cut from the OSM coastline and Lake Merritt treated as inland water.

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
| ART vs our bathtub (IoU, land) | 0.74 | 0.80 | 0.68 | 0.73 | n/a (66 in vs 60 in) |
| ART vs NOAA SLR Viewer (IoU, same level) | 0.62 | 0.68 | NOAA n/a† | 0.73 | NOAA 5.5 ft n/a† |
| Bathtub vs NOAA (IoU) | 0.64 | 0.67 | NOAA n/a† | 0.86 | 0.88 |
| Buildings flooded: ART / bathtub | 6 / 7 | 14 / 9 | 49 / 46 | 117 / 109 | 1,137 (66 in) / 417 (60 in) |

†NOAA's `slr_3ft` and `slr_5_5ft` services return a blank render for this area (checked 2026-11-21), so ART 66 in has no independent NOAA check. ART itself is validated at 1, 2 and 4 ft.
- A Port strip that NOAA treats as disconnected connects in our model through a single 1 m cell at an at-grade intersection, at +4.73 ft (`port_discrepancy_sill.png`). That's a threshold effect, not a missing seawall.
- The bathtub's ±0.196 m DEM-accuracy runs give 150–1,200 flooded buildings at 5 ft. West Oakland is flat around 3.4–3.7 m, so counts near that level are very sensitive.

## Limitations and assumptions

- Exploration tool, not an official hazard or evacuation map. Still-water flooding only: no storm surge, rainfall, groundwater rise, or compound events. A 100-year storm tide adds ~0.84 m; supplementary bathtub runs are in `hazard/bathtub_summary.json`.
- **Depth is estimated** (ART extent combined with LiDAR). "+5 ft" is ART's 5.5 ft map, so it overstates exactly 5 ft on purpose.
- **Residents per building** is an area-based estimate. **97% of building heights are estimated** (OSM rarely tags height here). Roblox buildings are boxes.
- Drive times are free-flow estimates by road class, with no traffic, signals or dispatch time. TIGER ring roads are treated as two-way. Fire stations are Oakland's only, so Alameda and Emeryville stations are missing; the bbox includes part of Alameda.
- Contaminated-site proximity **does not mean residents are exposed**.
- CalEnviroScreen 4.0 uses 2010 tracts and population uses 2020 tracts; they are joined per building.
- **Priority sensitivity:** with equal weights, one lost facility in a tract carries a full third of the exposure score. At +5 ft this ranks a tract with zero affected residents #2. Adjust `PRIORITY_WEIGHTS` if that's not the intended emphasis.
- Overpass (the OSM API) refused automated requests during the build, so facilities come from authoritative agency datasets and the outer road ring comes from TIGER.
- **FloodWatch:** 311 reports partly reflect who calls 311 (see its README). It covers Oakland only, so the Alameda and Emeryville parts of the study area have no FloodWatch data.
- **Roblox world:** box buildings, 1.12 m terrain cells, flat water surfaces per scenario. It's for exploring, not for measuring.

## Data sources (all accessed 2026-11-21)

Links and service endpoints below were checked on 2026-11-21. “Reachable” means the page or service returned a response; it does not revalidate the underlying dataset or its methods. The MTC/SFEI landing page returned HTTP 403 from this environment, so its access is blocked here.

| Data | Source | Link check (2026-11-21) |
|---|---|---|
| Flood hazard | [ART Bay Shoreline Flood Explorer](https://explorer.adaptingtorisingtides.org/home), SF Bay Conservation and Development Commission ([WMS service](https://mapserver.adaptingtorisingtides.org/cgi-bin/mapserv?map=/opt/slrviewer/mapfiles/bcdc.map), layers `inundation0/12/24/36/48/52/66`, `lowlying*`) | Reachable (HTTP 200) |
| Elevation | USGS 3DEP 1 m DEM, project CA_AlamedaCounty_2021_B21 (QL1, 10 cm RMSEz class; [project report](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/CA_AlamedaCounty_2021_B21/CA_AlamedaCo_3_2021/reports/Alameda_Technical_Data_Report_Final_Signed.pdf)) | Reachable (HTTP 200) |
| Tide datum | NOAA CO-OPS [9414750 Alameda datums](https://tidesandcurrents.noaa.gov/datums.html?id=9414750); [Extreme Water Levels](https://tidesandcurrents.noaa.gov/est/est_station.shtml?stnid=9414750) product | Reachable (HTTP 200) |
| Validation | NOAA Office for Coastal Management [Sea Level Rise Viewer](https://coast.noaa.gov/slr/); [dc_slr map service](https://coast.noaa.gov/arcgis/rest/services/dc_slr/slr_1ft/MapServer) | Reachable (HTTP 200) |
| Buildings, study-area roads, coastline | [OpenStreetMap](https://www.openstreetmap.org/), via OSMnx; © OpenStreetMap contributors (ODbL) | Reachable (HTTP 200) |
| Outer road ring | U.S. Census Bureau [TIGER/Line 2025 roads, Alameda County](https://www2.census.gov/geo/tiger/TIGER2025/ROADS/tl_2025_06001_roads.zip) | Reachable (HTTP 200) |
| Land use (residential parcels) | [MTC / SFEI Enhanced Existing Land Use 2020](https://www.sfei.org/data/sfei-enhanced-mtc-2020-land-use) | Link access blocked here (HTTP 403); search metadata was available |
| Fire stations | City of Oakland GIS, [OFD_Basemap FeatureServer](https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/OFD_Basemap/FeatureServer/5) | Reachable (HTTP 200) |
| Hospitals, clinics, nursing facilities | CDPH Licensed and Certified Healthcare Facilities (CalHHS), [FeatureServer](https://services5.arcgis.com/FlidZxdI0LGC9vAw/arcgis/rest/services/CDPH_LC_Facilities_Data/FeatureServer/0) | Reachable (HTTP 200) |
| Schools | California Department of Education, [California Public Schools 2024-25](https://services3.arcgis.com/fdvHcZVgB2QSRNkL/arcgis/rest/services/SchoolSites2425/FeatureServer/0) | Reachable (HTTP 200) |
| BART stations | City of Oakland GIS, [Bart_Stations FeatureServer](https://services.arcgis.com/9tC74aDHuml0x5Yz/arcgis/rest/services/Bart_Stations/FeatureServer/0) | Reachable (HTTP 200) |
| Contaminated sites | DTSC EnviroStor ([`Envirostor_Public_Data_Export`](https://services3.arcgis.com/Oy2JTCD10wkoelxS/arcgis/rest/services/Envirostor_Public_Data_Export/FeatureServer/0)); SWRCB GeoTracker ([`geotracker_sites_download`](https://gispublic.waterboards.ca.gov/portalserver/rest/services/Hosted/geotracker_sites_download/FeatureServer/371)) | Both reachable (HTTP 200) |
| Equity | [CalEnviroScreen 4.0](https://oehha.ca.gov/calenviroscreen/report/calenviroscreen-40) (OEHHA); 2020 Census tracts and places ([TIGERweb service](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Census2020/MapServer)) | Both reachable (HTTP 200) |
| Alignment check | [Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer) | Reachable (HTTP 200) |
| Flooding today (via FloodWatch, Kai) | OAK 311 service requests ([dataset `quth-gb8e`](https://data.oaklandca.gov/Infrastructure/Service-requests-received-by-the-Oakland-Call-Cent/quth-gb8e)), FEMA National Flood Hazard Layer ([FEMA Flood Map Service Center](https://msc.fema.gov/portal/home)), CDC/ATSDR SVI 2022 ([data and documentation](https://www.atsdr.cdc.gov/placeandhealth/svi/data_documentation_download.html)), and USGS 3DEP ([project report](https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/metadata/CA_AlamedaCounty_2021_B21/CA_AlamedaCo_3_2021/reports/Alameda_Technical_Data_Report_Final_Signed.pdf)). See `oakland-flood-vulnerability/README.md` | All four links reachable (HTTP 200) |

## How to run

```bash
/opt/homebrew/opt/python@3.14/bin/python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
pipeline/run_all.sh
```

All downloads are cached in `data/raw/`. After the first run, a full rerun takes about 4 minutes.

### Windows setup

From the repository root in Command Prompt, create the environment and install the requirements:

```bat
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

The shell runner is Bash, so on Windows run its scripts one by one in the same order from the repository root:

```bat
.venv\Scripts\python pipeline\01_fetch_osm.py
.venv\Scripts\python pipeline\01b_fetch_landuse.py
.venv\Scripts\python pipeline\01c_fetch_network_osm.py
.venv\Scripts\python pipeline\01d_fetch_facilities.py
.venv\Scripts\python pipeline\01e_fetch_tiger_roads.py
.venv\Scripts\python pipeline\01f_fetch_contamination.py
.venv\Scripts\python pipeline\02_fetch_hazard.py
.venv\Scripts\python pipeline\03_fetch_elevation.py
.venv\Scripts\python pipeline\04_building_heights.py
.venv\Scripts\python pipeline\04b_alignment_check.py
.venv\Scripts\python pipeline\hazard_bathtub.py
.venv\Scripts\python pipeline\05_flood_exposure.py
.venv\Scripts\python pipeline\05b_validate_hazard.py
.venv\Scripts\python pipeline\06_consequences.py
.venv\Scripts\python pipeline\07_equity_priority.py
.venv\Scripts\python pipeline\08_export_for_roblox.py
.venv\Scripts\python pipeline\08b_export_roblox_world.py
.venv\Scripts\python pipeline\09_findings_brief.py
.venv\Scripts\python pipeline\10_floodwatch_slr.py
.venv\Scripts\python pipeline\08c_import_floodwatch.py
```

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
| 8 | `08_export_for_roblox`, `08b_export_roblox_world` | `roblox/` (heightmap, terrain tiles, sharded buildings and roads, water rectangles, points, manifest), **`stats.json`** |
| 9 | `09_findings_brief` | `brief/findings_brief.md` |
| 10 | `10_floodwatch_slr` (Kai, K1) | `floodwatch/hex_slr.csv`: sea-level-rise exposure per FloodWatch block |
| 8c | `08c_import_floodwatch` (runs last) | `roblox/floodwatch.json`: FloodWatch layer for the 3D world |

Shared constants (bbox, datum, scenarios, ART levels, rules, weights, scale) are in `pipeline/config.py`. To build the 3D world from these outputs, see [`roblox/SETUP.md`](roblox/SETUP.md). The 76 MB of terrain tiles are gitignored and regenerated by `08b`.

## Team and repository layout

| Area | Owner | Where |
|---|---|---|
| Sea-level-rise pipeline + 3D Roblox world | Cooper (+ Claude Code) | `pipeline/`, `roblox/`, `brief/` |
| FloodWatch (flooding today) + flood-analysis tasks K1–K8 | Kai (+ agents) | `oakland-flood-vulnerability/`, `pipeline/10_*` and later, `data/processed/floodwatch/` |
| Glossary, presentation outline, Spanish findings (H1–H3) | Henry (+ agent) | `docs/` |
| `stats.json` checks, viewer viewpoints, README links (L1–L3) | Leo (+ agent) | `tests/`, `tools/`, `roblox/viewpoints.json` |

- Task plans: [`docs/delegation_plan_kai.md`](docs/delegation_plan_kai.md) and [`docs/delegation_plan_henry_leo.md`](docs/delegation_plan_henry_leo.md).
- The team's shared Google Doc mirrors these plans and holds the running work log. Ask a teammate for access.
- Rules for everyone (people and agents):
  - Work on a branch and open a PR into `main`.
  - Claim a task in the work log before starting it.
  - `stats.json` is the single source of truth for numbers.
  - Add new fields freely, but don't rename fields the viewer reads.
