# Oakland Sea-Level Rise & Flooding Simulator

Hackathon project (DataFest). Goal: a 3D, interactive model of Oakland's waterfront that shows which buildings, roads, and communities flood at different sea-level-rise scenarios, using real open data, and quantifies the impact.

Time budget is ~24 hours. Favor a working end-to-end demo over completeness. Commit often.

City-building techniques below are adapted from a playbook written during a full San Francisco build in Roblox Studio (terrain, ~180k buildings, roads, landmarks). Only the parts that fit a 24-hour flood demo are included; the rest are listed under "Stretch goals."

## Core question

> At 1, 2, 3, and 5 ft of sea-level rise, how many buildings and road segments flood in West Oakland / Jack London / Oakland waterfront, and which communities bear the most risk?

## Scope (keep it small)

- Study area: West Oakland, Jack London Square, and the Port/airport shoreline.
- Starting bounding box (adjust if needed): west -122.335, south 37.790, east -122.255, north 37.830.
- Flooding only. No wildfire, traffic, or agent simulation.
- Method: connected "bathtub" model (simple, explainable, honest about limits).
- Visual fidelity: clean and readable on a projector. Correct terrain, building massing, roads, and water matter. Windows, trees, textures, and hand-modeled landmarks do not.

## Tech stack

- Data pipeline: Python 3.11+ in a venv: `osmnx`, `geopandas`, `shapely`, `rasterio`, `numpy`, `scipy`, `pandas`, `pillow`.
- Viewer: Roblox Studio (Luau). The Python pipeline produces engine-agnostic files (GeoJSON, binary height tiles, JSON); Luau builds the 3D world from them.
- Studio access: if the Roblox Studio MCP plugin is connected, drive Studio directly with `execute_luau` (see "Working with Studio over MCP"). Otherwise, paste scripts by hand following `roblox/SETUP.md`.
- Output formats: GeoJSON for vectors, GeoTIFF for terrain (plus a PNG preview), binary tiles/JSON for Roblox, JSON for scenario stats.

## Architecture

```
python pipeline (height tiles, buildings/roads JSON, stats.json)  ──►  data/processed/  ──►  serve.py (127.0.0.1:8765)
                                                                                              │  GET files, POST /log
Roblox Studio (edit mode, MCP execute_luau or command bar)  ◄─────────────────────────────────┘
   • reads files with HttpService:GetAsync (throttled)
   • writes Terrain, creates building/road Parts, stores per-scenario flood data as attributes
   • save_place → the built world lives in the .rbxl
Play mode: FloodController + UI read only the attributes (no HTTP, no recomputation)
```

- **Build once in edit mode, then save.** The world (terrain, buildings, roads) is built by a one-time builder script and saved in the place file. At runtime, scripts only recolor parts and move water. This way the demo doesn't depend on the local server or on HTTP working during judging.
- **Server:** `pipeline/serve.py`, about 15 lines of `http.server` serving `data/processed/` on `127.0.0.1:8765`, with a `POST /log` endpoint that appends JSON lines to `data/processed/buildlog.jsonl` (build progress, errors, uploaded asset ids if meshes are used). The server stops when the terminal or agent session ends. If Studio reports `HttpError: ConnectFail`, restart it.

## Repo layout

```
data/raw/          # downloaded sources (gitignored if large)
data/processed/    # pipeline outputs consumed by the viewer (served by serve.py)
pipeline/          # python scripts, run in numbered order, plus serve.py
roblox/            # Luau source (modules + scripts) + SETUP.md
backups/           # local .rbxl snapshots (gitignored)
README.md
```

## Pipeline steps (build in this order)

1. `01_fetch_osm.py`: With OSMnx, pull building footprints (`building=*`, plus `building:part`), the drivable/walkable road network, and `natural=coastline` / `natural=water` for the bbox. Keep `building:levels`, `height`, `building` type, and road `lanes`, `width`, `bridge`, `tunnel`, `layer`. Save GeoJSON in EPSG:4326.
2. `02_fetch_elevation.py`: Get a DEM for the bbox from USGS 3DEP (1/3 arc-second or better; use the LiDAR-derived 1 m DEM if available). Use the GeoTIFF's own georeferencing and merge tiles with `rasterio.merge`. Don't stitch tiles by hand, because that caused seams in the SF build. Reproject to a local metric CRS (EPSG:26910, UTM 10N). Record the vertical datum (NAVD88). If the DEM's bay pixels are flat or nodata, fill them from NOAA bathymetry (or GEBCO), or apply a gentle offshore slope with a minimum depth, so the bay floor isn't a flat sheet.
3. `03_building_heights.py`: Estimate heights: use `height` if present, else `building:levels * 3.0 m`, else a default (e.g., 6 m, flagged as `height_estimated=true`). Report what fraction is estimated. Optional upgrade if time allows: Alameda County building footprints or assessor parcels (year built, use, stories) for better heights. If you add them, also apply the data-cleaning rules below.
4. `04_flood_model.py`: See "Flood model" below. Output per-scenario flooded raster plus per-building and per-road flood flags and depths.
5. `05_equity_overlay.py`: Join results to census tracts with CalEnviroScreen scores. Compute flooded buildings and population-weighted exposure by tract.
6. `06_export_for_roblox.py`: Convert results into Roblox-ready files in `data/processed/` (see "Roblox export format"), then run the export validation checks.

### Data-cleaning rules (from the SF build)

- **Check alignment early.** Before writing the flood model, overlay OSM roads and building footprints on the DEM hillshade and on an aerial (Esri World Imagery tiles work well) and look for offsets. Save the overlay image as `data/processed/alignment_check.png`.
- **Phantom footprints:** drop footprints that aren't real buildings (plazas, underground garages, tunnels, `building=roof` canopies, or anything with a LiDAR/height value under ~1 m). Otherwise they show up as fake buildings in the middle of streets and inflate the flooded-building count.
- **Duplicates:** OSM `building` outlines and `building:part` polygons overlap, and so do multiple footprint sources. Dedupe (e.g., drop a polygon that is >80% covered by another) so buildings aren't double-counted in the stats and don't z-fight in Roblox.
- **Post-survey buildings:** if you switch to a county/LiDAR footprint dataset, check its survey date. Buildings constructed after that date only exist in OSM. Diff the two and add the missing ones.
- Use a generic User-Agent for downloads (no personal email in requests).

## Flood model

Scenarios: sea-level rise of 0, 1, 2, 3, and 5 ft above current Mean Higher High Water (MHHW). Convert feet to meters (1 ft = 0.3048 m).

- Baseline water level: look up the current MHHW at the nearest NOAA CO-OPS station (San Francisco 9414290, or Alameda if closer) in NAVD88, and cite the value in the README. Keep everything (DEM, water levels, Roblox heights) in NAVD88 so the terrain and the water plane use the same datum.
- Water level for scenario $s$: $W_s = \text{MHHW}_{\text{NAVD88}} + \Delta_s$.
- A cell with ground elevation $z$ is flooded if $z < W_s$ **and** it is hydrologically connected to the bay. Implement connectivity with a flood fill (`scipy.ndimage.label`) seeded from open-water cells. This avoids falsely flooding low spots behind high ground.
- **Seed carefully.** Build the sea mask from OSM `natural=coastline` / water polygons, and seed the fill from **several points well out in open bay water** (e.g., mid-Oakland Estuary, the Outer Harbor, the open bay west of the Port). The SF build's sea mask flooded all of Oakland because of one bad seed point. Save a PNG of the sea mask and each scenario's flood mask and look at them before trusting the numbers.
- Flood depth: $d = \max(0,\; W_s - z)$.
- A building is flooded if the DEM cell(s) under its footprint have $d > 0$. Store max depth.
- A road segment is impassable if depth along it exceeds 0.15 m (about 6 in).
- Document the limitations clearly: no storm surge, rainfall, groundwater, or levee/pump modeling; DEM may not capture seawalls.

## Equity overlay

- Use CalEnviroScreen (latest version) tract-level scores and 2020 Census tract boundaries and population.
- Report, per scenario: number of flooded buildings, km of flooded road, estimated residents affected (building-area-weighted allocation of tract population is fine), and which high-burden tracts (top quartile CalEnviroScreen) are hit hardest.

## Roblox export format

- **One projection, used everywhere.** Convert everything to meters in EPSG:26910, then subtract the bbox southwest corner so the origin is (0, 0). Roblox axes: X = east, Z = −north (negate northing), Y = up.
- **Scale:** put the scale in one constant, `STUDS_PER_METER`, shared by Python and Luau, and never hard-code it elsewhere. Default: 1 stud = 0.28 m, so `STUDS_PER_METER = 1 / 0.28` (≈ 3.571). The SF build calibrated instead against an R15 avatar (5′10″ = 1.778 m), giving `STUDS_PER_METER = 2.9196`. Either works; pick one before building and don't change it.
- **Size check:** at 0.28 m/stud the default bbox is about 7.0 km × 4.4 km ≈ 25,000 × 15,700 studs. That is fine for Terrain, but it affects the water and chunking rules below.
- **Terrain:** Luau can't decode PNG files, so export heights as **binary tiles** that Luau reads with the `buffer` library. Use one file per tile, e.g. `terrain/tile_<i>_<j>.bin` covering 128 × 128 voxel columns, with a little-endian header `u16 cols, u16 rows` followed by `u16` heights. Store `elev_min_m` and `elev_max_m` in `stats.json` so heights map back to meters: $z = z_{\min} + \tfrac{v}{65535}(z_{\max}-z_{\min})$. Also store a per-column material byte (pavement under roads, grass in parks, sand on beaches, mud on tidal flats, rock on steep slopes). Resample the DEM so that one column is one 4-stud Roblox voxel, or coarser if the build is slow; extra resolution is wasted. Also write a 16-bit grayscale `heightmap.png` as a preview and as a manual fallback (Studio's Terrain Editor can import heightmap images).
- **Buildings:** export per building: `id`, `cx`, `cz`, `width`, `depth`, `rotation_deg` (from shapely `minimum_rotated_rectangle`), `height_m`, `base_elev_m` (the **lowest** ground under the footprint), `height_estimated`, `flood_depth_m` per scenario (array aligned to the scenario list), and `tract_id` / CalEnviroScreen percentile. Shard by grid cell (e.g., 1 km) so each file stays well under 1 MB and HTTP reads stay small.
- **Roads:** export as polylines (lists of x, z, elevation) with `width_m` (from `width`, or `lanes × 3.5 m`, or a default by highway type) and a per-scenario `impassable` flag array. Shard by the same grid.
- **Water:** export each scenario's flood extent as per-tile liquid masks in the same tile grid as the terrain (bit-packed or as a `u8` depth in voxels). These are used by the optional terrain-water mode below.
- Also write `stats.json` with the per-scenario totals and tract table so the Roblox UI numbers are exactly the pipeline's numbers.
- **Export validation** (end of `06_export_for_roblox.py`): no NaN coordinates; every building is inside the bbox; widths and heights are positive; per-scenario arrays have exactly 5 entries; the number of flooded buildings in the JSON files equals the totals in `stats.json`; shard sizes are printed.

## Roblox Studio requirements

Deliver Luau source under `roblox/` and a short `roblox/SETUP.md` listing exactly where each script goes (ServerStorage, ServerScriptService, StarterPlayerScripts, StarterGui, and so on), how to start `serve.py`, and how to run the builder.

### Modules (keep in `ServerStorage` and also on disk under `roblox/`)

- `Config`: `STUDS_PER_METER`, origin, scenario list, color ramps, server URL. This is the single source of shared constants.
- `DataLoader`: `HttpService:GetAsync` against `http://127.0.0.1:8765/...`. Throttle to stay under HttpService's ~500 requests/min budget (`task.wait(0.14)` between files). Retry once on failure, and POST progress and errors to `/log`.
- `TerrainWriter`: reads height tiles and writes them with `Terrain:WriteVoxelChannels` (`SolidMaterial`, `SolidOccupancy`, `LiquidOccupancy`) in 64 × 64 sub-blocks with `task.wait()` between them. Terrain is only a **crust** a few voxels thick below the surface, which keeps memory reasonable. Fill bay voxels with liquid up to the baseline (MHHW) level. Simpler fallback: `FillBlock` per column, or the Terrain Editor heightmap import.
- `WorldBuilder`: one anchored Part per building (`CanCollide = false`, `CanQuery = true` so it can be clicked, named by building id, `CFrame` from `cx`, `cz`, `rotation_deg`, sunk ~1 m below `base_elev_m` so it doesn't float on slopes). It also stores the flood data on the part as **attributes**: `FloodDepth1..5`, `CES`, `TractId`, `HeightEstimated`. Roads are thin anchored Parts between consecutive points with per-scenario `Impassable1..5` attributes. Buildings go in `workspace.City.Buildings/<cell>` and roads in `workspace.City.Roads/<cell>`, with one Folder per grid cell.
- `Verify`: checks after building (see "Verify before calling it done").

### Scripts

- **Builder (run once, in edit mode):** runs the modules for a chosen region (sub-area first). It is **resume-aware**: it skips cells whose folder already exists and is marked complete with a `Done` attribute, so a dropped connection or a timeout doesn't mean starting over. Progress goes to `workspace.City:SetAttribute("Progress", "cells 12/40")`.
- **Water (runtime):** a single Part can be at most 2048 studs on a side, which is smaller than the study area. Use a **grid of water Parts** (e.g., 2000 × 2000-stud tiles, semi-transparent blue, `CanCollide = false`) whose Y follows the selected scenario: $Y = W_s \cdot \text{STUDS\_PER\_METER}$, in the same NAVD88-based frame as the terrain. Tween the change so the rise is visible.
  - Known artifact: a flat plane also appears in low spots the connected model says stay dry, such as areas behind high ground. Either say so in the presentation, or use the optional **terrain-water mode**: on scenario change, write `LiquidOccupancy` from the precomputed per-scenario liquid masks, so water appears only where the model floods. Do this one tile at a time with `task.wait()`, and cache it so switching back is fast.
- **FloodController (runtime):** when the scenario changes, recolor each building from its `FloodDepth<s>` attribute (gray = dry, light blue to dark blue = shallow to deep) and turn impassable roads red. Do it in one batched pass with `task.wait()` every ~2,000 parts. Use only the precomputed attributes, and don't recompute floods in Luau. A toggle colors buildings by CalEnviroScreen burden instead.
- **UI (ScreenGui):** buttons or a slider for 0, 1, 2, 3, and 5 ft, plus a live stats panel (flooded buildings, flooded road km, residents affected) and a legend. Read the numbers from a `Stats` ModuleScript generated from `stats.json`, so they match the pipeline exactly. Keep fonts large and readable on a projector. Optional: click a building to see its depth, height (flagged if estimated), and tract.
- **Camera:** no character (`Players.CharacterAutoLoads = false`). Use a smooth free-fly camera with eased look and velocity, scroll to change speed tiers, and Shift for ×5 speed. Add a reset-to-overview button and saved viewpoints (West Oakland, Jack London, Port). With streaming on, a server-side `ReplicationFocus` part follows the camera so content loads around it.
- **Lighting (cheap wins):** `Lighting.Technology = Future`, an `Atmosphere` with light haze, and a fixed midday `ClockTime`. Skip the day/night cycle.

### Performance

- Keep every part anchored, don't run per-frame loops over buildings, and recolor only on scenario change.
- If the part count gets high, set `StreamingEnabled` with `StreamingTargetRadius` ~ 12000, `StreamingMinRadius` ~ 2000, and `StreamOutBehavior = Opportunistic` so the whole waterfront is visible from overview height.
- Big edits freeze Studio, for example recoloring or moving tens of thousands of parts at once. Always batch with `task.wait()`.

### Optional upgrade: true footprints as meshes

Rotated rectangles are good enough for the demo. If time allows, real footprint shapes can be extruded in Python, written as mesh chunks, and uploaded via `AssetService:CreateEditableMesh()` → `CreateAssetAsync(em, Enum.AssetType.Mesh)` → `CreateMeshPartAsync(Content.fromAssetId(id))`. Rules learned the hard way in the SF build:

- Mesh limits: ≤ 10k triangles, ≤ 25k vertices, ≤ ~2,000 studs extent per chunk, or pieces go missing. Auto-split chunks that are too big.
- Set the Position to the chunk's source origin, not its bounds center.
- Roblox's front-face winding is the opposite of a naive cross product, so test with a cube first, because otherwise buildings come out inside-out.
- Uploads are rate-limited to ~40/min. **Log every asset id** to `/log` and write a `Restore` module that re-places meshes from the log without re-uploading.
- Visual meshes should be `CanCollide = false`, `CanQuery = false`, and `CollisionFidelity = Box`.
- Catch for this project: vertex colors are baked at upload, so meshes can't be recolored per scenario. Keep the invisible Parts (or one thin colored roof Part per building) as the per-building flood layer, or use meshes only for context outside the study area.

## Working with Studio over MCP

- Run long jobs inside Studio with `task.spawn`, then poll the `Progress` attribute with short MCP calls. MCP calls time out after ~60 s, so never run a whole build in one call.
- If the MCP link drops (common on network changes), Studio keeps running. Toggle the MCP server in Studio's Assistant settings, check the current state, and resume. Don't blindly re-run, because the builder is resume-aware.
- After a timeout, check what state Studio is in before running anything again.
- **Never leave debug state behind.** Restore hidden parts, moved folders, `LocalTransparencyModifier` tweaks, and test patches in the same step.
- Use `screen_capture` from a few viewpoints to check the result visually.

## Save discipline

- Call `save_place` (or File → Save) at every checkpoint: after terrain, after buildings, after roads, after the UI works.
- **Verify the save.** Team Create saves can fail silently, and in the SF build Studio once reopened a version from hours earlier after a restart. Also export a local `.rbxl` to `backups/` at each checkpoint (`oakland_<step>_<time>.rbxl`).
- Restart Studio after big build sessions if it gets sluggish.

## Verify before calling it done

- **Water check:** sample terrain along a few transects (Estuary, Outer Harbor, open bay) and confirm the bay has liquid voxels, not mud, below baseline. Rewrite any bad tiles.
- **Alignment check:** fly over and confirm roads sit on the terrain and buildings sit on their roads. Look for buildings floating on slopes or sunk into the ground.
- **Numbers check:** for each scenario, count parts whose `FloodDepth<s>` is greater than 0 and compare with `stats.json`. The counts must match exactly.
- **Spot check:** compare a few flooded locations against NOAA's Sea Level Rise Viewer and note discrepancies in the README.
- **Fly around** from street level and overview before calling anything done. Common problems in the SF build were floating geometry, z-fighting duplicates, buildings inside streets, mud where water should be, and too-short draw distance.

## Definition of done (priority order)

1. Pipeline runs end to end and writes `stats.json`.
2. Roblox Studio scene shows 3D terrain and buildings, with a working scenario-driven water level, and is saved (local `.rbxl` backup verified).
3. Stats panel and legend are accurate and match `stats.json`.
4. Equity overlay works.
5. README has: data sources with access dates, method, limitations, and how to run.

## Working agreements

- Verify data source URLs and current download methods before coding against them; do not guess endpoints.
- Cache downloads in `data/raw/`; never re-download on every run or in a loop.
- Validate results: spot-check a few flooded locations against NOAA's Sea Level Rise Viewer and report discrepancies.
- Flag any assumption or estimated value (building heights, datum conversions, scale choice) rather than hiding it.
- Use American English spelling in all docs and UI text.
- Test the Luau scripts in Studio on a small sub-area first (for example, a few blocks around Jack London Square) before building the full bbox.
- If you have no direct access to Roblox Studio, write the scripts and `SETUP.md` carefully and say what still needs to be run by hand.
- If something blocks progress for more than ~30 minutes, simplify scope (for example, drop the equity overlay, use a smaller bbox, or skip terrain-water mode) and note it.

## Suggested build order

1. Bbox and scale constant agreed → data download → alignment check.
2. Flood model and sea mask (look at the mask PNGs) → equity overlay → export and validation.
3. Start `serve.py` → Studio: terrain for a sub-area → verify water → **save**.
4. Buildings and roads for the sub-area → FloodController and water → **save**.
5. UI, camera, viewpoints → full bbox → streaming settings → **save + backup**.
6. Verification pass and README. Then stretch goals if time remains.

## Stretch goals (only after the definition of done is met)

- Terrain-water mode (connected flooding shown accurately).
- True footprint meshes (see the optional upgrade above).
- One or two simple landmark models for orientation (e.g., Port of Oakland cranes, Jack London Square), built from boxes on their real OSM footprints.
- Street trees in parks only, on cells not covered by building footprints, without shadows.
- Comparison layer with Our Coast Our Future (CoSMoS) projections.

## Data sources to use

- OpenStreetMap via OSMnx (ODbL; credit "© OpenStreetMap contributors"), including `natural=coastline` for the sea mask.
- USGS 3DEP elevation data.
- NOAA bathymetry (or GEBCO) for the bay floor.
- NOAA CO-OPS tide datums and the NOAA Sea Level Rise Viewer (for validation).
- CalEnviroScreen (CA OEHHA) and U.S. Census tract data.
- Esri World Imagery tiles (alignment check only).
- Optional: Alameda County building footprints / assessor parcels, the Oakland open data portal, Our Coast Our Future (CoSMoS) projections for comparison.
