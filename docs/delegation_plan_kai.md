# Delegation plan: flood analysis for Kai's agents

> **Update 2026-11-21:** the Roblox viewer was dropped; the FloodWatch website is the demo. Roblox parts below (the `roblox/` folder, viewer contract, L2 viewpoints) no longer apply. The building export moved to `data/processed/export/` (step `08_export`). Current plan: section 19 of the team doc.

*Created 2026-11-21. Mirrors section 14 of the team Google Doc. Keep both in sync.*

## Why this split

- **Cooper (+ Claude Code)** is building the 3D Roblox viewer. The viewer reads `data/processed/roblox/` and `data/processed/stats.json`.
- **Kai (+ his agents)** works in Jupyter. His **Oakland FloodWatch** notebook (`oakland-flood-vulnerability/`) already covers citywide *rain and storm-drain* flooding today: 311 reports, an ML model, FEMA zones, CDC SVI.
- Our main pipeline (`pipeline/`) covers *sea-level-rise* flooding and its consequences in West Oakland.
- The flood analysis below goes to Kai's agents, so the two analyses combine into one story: **"West Oakland already floods when it rains; sea-level rise turns that into permanent flooding, cut-off streets and contaminated ground."**

## Ownership: who touches what

| Area | Owner | Rule |
|---|---|---|
| `roblox/`, `data/processed/roblox/` schema, `pipeline/08_export_for_roblox.py` | Cooper | Others: don't edit. Ask in the doc if you need a new field shown. |
| `oakland-flood-vulnerability/`, new notebooks, new `pipeline/10_*.py` and later scripts | Kai | Cooper's agent won't edit these. |
| `pipeline/05`–`07` (exposure, consequences, priority) | Kai, for tasks K1–K8 | Coordinate in the doc before changing outputs Cooper's viewer reads. |
| `pipeline/config.py`, `stats.json` schema | Shared | **Additive only**: add new keys freely, but never rename or remove existing ones without a note in the doc and Cooper's OK. |

### The contract Cooper's viewer depends on (don't break it)

- `stats.json` → `scenario_ids`, `scenarios[*]` (fields `id`, `slr_ft`, `water_level_navd88_m`, `water_level_studs`, `buildings_flooded`, `residents_affected`, `facilities_lost`, `residents_cut_off`, `residents_degraded`, `contaminated_sites_near_flooding`, `road_km_impassable`), `top_priority`, `terrain`, `studs_per_meter`.
- Building shards → `id, cx, cz, w, d, rot, h, base, depth[6], flooded, cut, deg, contam, low, pri[6], tract, ces, res`. The flags are 6-character strings, one per scenario (0, 1, 2, 3, 4, 5 ft).
- The 6 scenarios stay `0ft`…`5ft`, and "5ft" = ART 66 in. Extra scenarios (for example storm runs) go under **new** keys.

## Tasks for Kai's agents (priority order)

Each task: branch `kai/<task-id>`, a notebook in `oakland-flood-vulnerability/notebooks/` for exploration, final logic in a script so `pipeline/run_all.sh` reproduces it, outputs in `data/processed/floodwatch/`. **Claim the task in the doc's work log before starting**, and log the commit hash when done.

### K1. Bring sea-level-rise exposure into FloodWatch hexes *(highest)*
- **Goal:** for each H3 hex in our study area, report the share flooded and the buildings and residents affected at 0–5 ft, so FloodWatch's map can show "today's rain flooding" next to "future sea-level-rise flooding". This is also on Kai's own next-steps list.
- **Inputs:** `data/processed/flood_depth_<ft>ft.tif` (run `pipeline/run_all.sh` once; the rasters are gitignored) and `data/processed/buildings_final.geojson`.
- **Output:** `data/processed/floodwatch/hex_slr.csv` (h3, scenario, flooded_share, buildings_flooded, residents_affected).
- **Done when:** the per-hex totals sum to `stats.json` totals for each scenario.

### K2. "It already floods": 311 rain flooding as a layer for the viewer
- **Goal:** export Kai's hex scores (FVI, report counts, "why") for the study area in our Roblox frame, so Cooper can add a **"Flooding today"** map mode.
- **Output:** `data/processed/floodwatch/hexes_roblox.json`, with hex center x/z in our local frame (EPSG:26910 minus 558520, 4182723; Z = −north), radius in meters, fvi, flood_reports. Cooper wires it into the viewer.
- **Done when:** the file loads and the hex centers line up with the study-area buildings (plot both).

### K3. Rain + tide: do king tides make storm-drain flooding worse?
- **Goal:** join daily 311 flood reports with NOAA tide highs at **Alameda 9414750** (our datum station; MHHW = 1.941 m NAVD88) and daily rainfall. Test whether reports per inch of rain rise when high water is above MHHW. This is the evidence that sea-level rise worsens drainage flooding, not just shoreline flooding.
- **Output:** a notebook, plus one figure for the brief (`brief/figures/rain_tide.png`) and a short result paragraph posted in the doc.

### K4. Who can't evacuate: SVI detail for cut-off residents
- **Goal:** join CDC SVI 2022 variables (no vehicle, disability, age 65+, limited English) to buildings cut off from emergency services in `buildings_final.geojson` (`cut_off_<ft>ft`, `residents_est`).
- **Output:** a new `stats.json` key `cut_off_vulnerability` per scenario (additive).
- **Done when:** the numbers are reported against Oakland-wide baselines, the same way the equity section does it.

### K5. Fix the priority-score quirk + sensitivity test
- **Problem:** `facilities_lost` counts facilities *inside* a tract, so at 5 ft a tract with 0 affected residents can rank highly.
- **Do:** replace it with residents whose nearest fire station or medical facility is lost (service area), using the travel-time outputs from `06_consequences.py`. Then test 4–5 weight sets and report how stable the top 5 is.
- **Also:** compare our priority tracts with FloodWatch's FVI tract ranking (`outputs/tract_scores.csv`). Where they agree, that's a strong finding.
- **Output:** updated `pipeline/07_equity_priority.py` (same output keys), a sensitivity table in the doc.

### K6. Groundwater rise + "hidden risk" buildings
- **Goal:** find and verify the regional shallow-groundwater-response-to-sea-level-rise layer for Alameda County (don't guess the endpoint). Flag buildings and contaminated sites where groundwater emerges or gets very shallow at each scenario. Compare against ART's "low-lying" buildings (422 at 4 ft).
- **Output:** new per-building fields (additive) plus a summary in `stats.json`, for example `groundwater`.

### K7. Validation spot checks
- **Goal:** at 8–10 named places (Jack London Square, Howard Terminal, Brooklyn Basin, Mandela Pkwy/7th St, Prescott, the Bay Bridge toll plaza shore, Fire Station 2), compare ART Explorer, NOAA SLR Viewer and our estimated depth. Add the Nov 18, 2026 storm 311 reports for West Oakland.
- **Output:** a table in the README's Validation section.

### K8. Fill facility gaps (lower priority)
- Add Alameda and Emeryville fire stations, AC Transit bus stops (GTFS) and shelters, from verified sources. Rerun `06`, and report how the cut-off counts change.

## How Kai's agents should work

1. Read `README.md`, `new.md` (the project plan) and this file. Run `pipeline/run_all.sh` once (about 4 minutes; downloads are cached in `data/raw/`).
2. Claim a task in the doc's work log: `YYYY-MM-DD Kai's agent: claiming K#`.
3. Work on branch `kai/K#` and open a pull request into `main`. Don't push directly to `main`.
4. Verify data endpoints before using them, cache downloads, and flag every assumption.
5. When done, log the result, the commit hash and any new `stats.json` keys in the doc.
6. If a task needs a change to the viewer contract above, post in the doc's "Open questions" section and wait for Cooper.
