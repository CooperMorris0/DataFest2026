# Oakland Flood Consequence Explorer (Roblox)

Hackathon project (DataFest). A 3D, walkable Roblox model of West Oakland and the nearby waterfront that shows what sea-level rise *means for people*, built on real open data.

Time budget is ~24 hours. Favor a working end-to-end demo over completeness. Commit often.

## Audience and impact (read this first)

- **Primary audience:** West Oakland residents, especially students and community groups. They get an experiential, walk-your-own-street view of flooding and its consequences, in a tool teens will actually use.
- **Secondary audience:** City and regional planners. The city's Subregional Shoreline Adaptation Plan is collecting community input and evaluating risk during 2026–2027, so our findings brief is a timely, concrete input.
- **Pitch line:** "Official flood maps show where water goes. We show what it means for the people who live there, and where help should start."

### How this differs from existing tools (do not duplicate them)

- Existing: the ART (Adapting to Rising Tides) Bay Shoreline Flood Explorer, the NOAA Sea Level Rise Viewer, and Oakland's 2017 Sea Level Rise Roadmap. These are mostly 2D, planner-oriented hazard maps.
- Our hazard data comes FROM the ART flood layers. We do not build a competing flood model.
- Our added value is three layers on top of that hazard data:
  1. **Experiential 3D:** walk a real street at 1 to 5 ft of sea-level rise.
  2. **Consequences:** critical facilities hit, neighborhoods cut off from emergency services, and flooded areas near contaminated sites.
  3. **Equity-weighted priorities:** rank blocks or tracts by who needs help first.

## Core questions

> At 1, 2, 3, 4, and 5 ft of sea-level rise in West Oakland, (a) how many residents, buildings, and critical facilities are affected, (b) which areas lose access to emergency services, (c) which flooded areas are near contaminated sites, and (d) which neighborhoods should be prioritized?

## Scope (keep it small)

- Study area: West Oakland, Jack London Square, and the Port shoreline.
- Starting bounding box (adjust if needed): west -122.335, south 37.790, east -122.255, north 37.830.
- Flooding only. No wildfire or agent simulation.
- Hazard: ART flood layers (primary). Our own simplified connected-bathtub model on a LiDAR DEM is a FALLBACK only, used if ART data can't be loaded in time.

## Tech stack

- Data pipeline: Python 3.11+, `osmnx`, `networkx`, `geopandas`, `shapely`, `rasterio`, `numpy`, `scipy`, `pandas`, `requests`.
- Viewer: Roblox Studio (Luau). The Python pipeline produces engine-agnostic files (GeoJSON, PNG heightmap, JSON); Luau scripts in Roblox Studio build the 3D world from them.
- Output formats: GeoJSON for vectors, PNG for the heightmap, JSON for scenario stats.

## Repo layout

```
data/raw/          # downloaded sources (gitignored if large)
data/processed/    # pipeline outputs consumed by Roblox
pipeline/          # python scripts, run in numbered order
roblox/            # Luau scripts (world builder, flood controller, UI) + SETUP.md
brief/             # one-page findings brief for planners (markdown or PDF)
README.md
```

## Pipeline steps (build in this order)

1. `01_fetch_osm.py`: With OSMnx, pull building footprints, the drivable road network, and critical facilities for the bbox. Facilities: `amenity` in school, hospital, clinic, doctors, fire_station, police, shelter-type tags, plus `public_transport` stops and BART stations. Keep `building:levels`, `height`, and `building` type. Save GeoJSON in EPSG:4326.
2. `02_fetch_hazard.py`: Load ART Bay Shoreline Flood Explorer flood data for the bbox for sea-level-rise scenarios of 12, 24, 36, 48, and 60 inches above MHHW (plus the 0-inch baseline), and for temporary versus permanent flooding if available. Find the current download or ArcGIS REST service from the official ART site or the California open data portal. Verify the URL and the scenario names actually available, and do not guess endpoints. Record each layer's description and date for the README. If ART layers include flood depth, use it. If they are polygons only, flag buildings and roads as flooded or not and skip depth.
3. `03_fetch_elevation.py`: Get a DEM from USGS 3DEP for the bbox (1 m LiDAR-derived if available). Reproject to EPSG:26910. Needed for the Roblox terrain, and for the fallback flood model.
4. `04_building_heights.py`: Estimate heights: `height` if present, else `building:levels * 3.0 m`, else a default of 6 m flagged `height_estimated=true`. Report the share that is estimated.
5. `05_flood_exposure.py`: Intersect buildings, road segments, and facilities with each scenario's flood layer. Output per-scenario flags (and depth if available).
6. `06_consequences.py`: Run the three consequence analyses described below.
7. `07_equity_priority.py`: Join to census tracts with CalEnviroScreen and compute the priority score.
8. `08_export_for_roblox.py`: Write Roblox-ready files plus `stats.json` and a tract table.
9. `09_findings_brief.py` (or by hand): Generate the planner-facing one-page brief from `stats.json`.

If ART data can't be loaded, fall back to this bathtub model, and say so in the README: water level $W_s = \text{MHHW}_{\text{NAVD88}} + \Delta_s$ (look up MHHW at the nearest NOAA CO-OPS station). A cell with ground elevation $z$ is flooded if $z < W_s$ and it is hydrologically connected to the bay (flood fill with `scipy.ndimage.label`). Depth is $d = \max(0,\; W_s - z)$.

## Consequence analyses

### A. Critical facilities
For each scenario, list which schools, clinics, hospitals, fire stations, shelters, and transit stops are in flooded areas. Report counts and names.

### B. Isolation analysis (emergency access)
- Build the drivable network with OSMnx and set travel-time weights.
- For each scenario, remove road edges that are flooded (or, if depth is available, deeper than 0.15 m).
- For every residential building or network node, compute travel time to the nearest fire station and nearest hospital or clinic, before and after flooding.
- Flag **cut off** (no path) and **degraded** (travel time more than doubles).
- Report residents and buildings affected, and a map layer for Roblox.
- Treat facilities that are themselves flooded as unavailable.

### C. Contamination proximity
- Get contaminated-site locations from California's public cleanup databases (EnviroStor and GeoTracker). Verify the current download method, and keep only sites in or near the bbox.
- For each scenario, flag sites inside or within about 100 m of flooded areas, and count residents within that buffer.
- This is **proximity, not proof of exposure**. Word it carefully in the UI and the brief.

## Equity and priority score

- Use CalEnviroScreen (latest version) tract scores and 2020 Census tract boundaries and population.
- Estimate residents per building by allocating tract population by building footprint area (document this assumption).
- Priority for tract or block $i$, per scenario:

$$\text{Priority}_i = \text{Exposure}_i \times \text{Vulnerability}_i$$

where Exposure combines the share of flooded buildings, facilities lost, and residents cut off (normalize each to 0–1 and average), and Vulnerability is the CalEnviroScreen percentile scaled to 0–1. Document the weights and keep them as named constants.
- Report the top 5 priority areas per scenario.

## Roblox export format

- Local coordinates: convert to meters in EPSG:26910, then subtract the bbox southwest corner so the origin is (0, 0). Roblox axes: X = east, Z = south (negate northing), Y = up.
- Scale: 1 stud = 0.28 m. Put it in one constant, `STUDS_PER_METER = 1 / 0.28`.
- Terrain: a 16-bit grayscale heightmap PNG (at most about 2048 x 2048 cells; Roblox voxels are 4 studs), plus min and max elevation in `stats.json`.
- Buildings: approximate each footprint with its minimum rotated rectangle (shapely `minimum_rotated_rectangle`). Per building: `id`, `cx`, `cz`, `width`, `depth`, `rotation_deg`, `height_m`, `base_elev_m`, `height_estimated`, per-scenario `flooded` flags (and `flood_depth_m` if available), `cut_off` and `degraded` flags per scenario, `tract_id`, and the CalEnviroScreen percentile.
- Roads: polylines (x, z, elevation) with per-scenario `impassable` flags.
- Facilities and contaminated sites: points with `type`, `name`, and per-scenario `flooded` or `near_flood` flags.
- Keep `buildings.json` under a few MB, and shard by grid cell if larger.
- `stats.json`: per-scenario totals, the tract table, and the top priority areas, so the UI numbers match the pipeline exactly.

## Roblox Studio requirements

Deliver Luau source under `roblox/` and a short `roblox/SETUP.md` saying where each script goes (ServerScriptService, StarterGui, and so on) and how to load the data.

- Data loading: run `python -m http.server` in `data/processed/` and use `HttpService:GetAsync` from a Server Script, with "Allow HTTP Requests" enabled in Game Settings > Security (Studio use only). If that is unreliable, fall back to ModuleScripts with sharded JSON.
- World builder (Server Script): fill terrain from the heightmap using `workspace.Terrain`, then create one anchored, non-colliding Part per building and thin Parts for roads. Add markers for facilities and contaminated sites. Build in batches with `task.wait()` to avoid freezing Studio.
- Water: a large semi-transparent blue Part whose height follows the chosen scenario (or terrain water if it works well).
- Scenario controller: on scenario change, recolor buildings and roads from the precomputed flags. Never recompute floods in Luau.
- Map modes (toggle in the UI): (1) Flood, (2) Cut off from emergency services, (3) Contamination proximity, (4) Priority by equity. Each mode has its own legend.
- UI (ScreenGui): scenario buttons for 0, 1, 2, 3, 4, and 5 ft; a live stats panel (residents affected, buildings flooded, facilities lost, residents cut off, contaminated sites near flooding); the legend; and a "Top priority areas" list. Use large fonts that read on a projector.
- Walk mode: let the player walk the streets at ground level, and add a few saved viewpoints (West Oakland, Jack London, Port) plus a reset-to-overview button.
- Performance: use `StreamingEnabled` if the part count gets high, keep parts anchored, and avoid per-frame loops over all buildings.

## Findings brief (for planners)

A one-page brief in `brief/` with: the top findings per scenario, the top 5 priority areas, a map screenshot from Roblox, the method in 3 sentences, and the limitations. Frame it as input to the city's shoreline adaptation planning, not an official assessment.

## Limitations to state clearly (in the README, the brief, and the UI)

- This is a simplified exploration tool, not an official hazard or evacuation map. Defer to ART, BCDC, and city plans.
- Groundwater rise, rainfall flooding, and compound events may add risk that our layers do not fully capture. If a groundwater layer is available from the regional shallow-groundwater study, note it as future work or include it as an optional layer.
- Contaminated-site proximity does not mean residents are exposed.
- Residents per building is an area-based allocation, so it is approximate.
- Building heights are partly estimated. Roblox buildings are box approximations.

## Definition of done (priority order)

1. Pipeline runs end to end with real hazard data and writes `stats.json`.
2. Roblox scene shows terrain and buildings, with a working scenario-driven flood view.
3. Isolation analysis works and appears as a map mode, because it is the strongest differentiator.
4. Equity priority mode and the top-priority list work.
5. Contamination proximity mode works.
6. Findings brief and README (sources with access dates, method, limitations, how to run).

If time runs short, cut in this order: contamination mode, then the groundwater note, then walk-mode polish. Do not cut the isolation analysis or the equity priority.

## Working agreements

- Verify data source URLs and download methods before coding against them. Do not guess endpoints.
- Cache downloads in `data/raw/`. Never re-download on every run.
- Validate: spot-check a few flooded locations against the ART Flood Explorer and the NOAA Sea Level Rise Viewer, and report any discrepancies.
- Flag every assumption and estimate rather than hiding it.
- Use American English spelling in all docs and UI text.
- Test the Luau scripts in Studio on a small sub-area (a few blocks) before building the full bbox.
- If you have no direct access to Roblox Studio, write the scripts and `SETUP.md` carefully and state what must be run by hand.
- If something blocks progress for more than about 30 minutes, simplify the scope and note it.

## Data sources

- ART Bay Shoreline Flood Explorer and its downloadable flood layers (BCDC / ART program).
- OpenStreetMap via OSMnx (ODbL; credit "© OpenStreetMap contributors").
- USGS 3DEP elevation data.
- NOAA CO-OPS tide datums and the NOAA Sea Level Rise Viewer (validation and fallback model).
- CalEnviroScreen (CA OEHHA) and U.S. Census tract data.
- California EnviroStor and GeoTracker (contaminated sites).
- Optional: the regional shallow-groundwater response layers, and the Oakland open data portal.
