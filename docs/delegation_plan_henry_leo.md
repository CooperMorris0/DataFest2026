# Small tasks for Henry's and Leo's agents

> **Update 2026-11-21:** the Roblox viewer was dropped; the FloodWatch website is the demo. Roblox parts below (the `roblox/` folder, viewer contract, L2 viewpoints) no longer apply. The building export moved to `data/processed/export/` (step `08_export`). Current plan: section 19 of the team doc.

*Created 2026-11-21. Mirrors section 15 of the team Google Doc. Keep both in sync.*

These tasks are **deliberately small** (about 30-60 minutes each for an AI agent on a free model). Each one:
- touches only the files it lists,
- needs no changes to `pipeline/`, `roblox/` scripts or `stats.json`,
- has a clear "done when" check.

Who owns the rest: Cooper = Roblox viewer, Kai = flood analysis (section 14 / `docs/delegation_plan_kai.md`).

## Rules for every task (please read)

1. **Claim it first:** add a line to the Google Doc work log, e.g. `2026-11-21 Henry's agent: claiming H1`.
2. **Branch:** `git checkout -b henry/H1` (or `leo/L2`, etc.). Open a pull request into `main` when done. Don't push to `main`.
3. **Only edit the files listed in the task.** If you think something else needs changing, write it in the doc's "Open questions" instead.
4. **Numbers:** copy them exactly from `data/processed/stats.json` or `brief/findings_brief.md`. Never invent or round numbers differently.
5. **When done:** log what you did and the commit hash in the doc's work log.
6. American English (except the Spanish translation task). Plain words: the audience includes West Oakland teens and residents.

---

## Henry's agent: resident-facing writing

### H1. Plain-language glossary
- **Create:** `docs/glossary.md`
- **What:** 15-20 terms a resident would trip over, each explained in 1-2 short sentences with no jargon. Include at least: sea-level rise, MHHW ("today's average high tide"), NAVD88, ART (Adapting to Rising Tides), flood extent, flood depth, "cut off" from emergency services, "degraded" access, CalEnviroScreen, high-burden tract, census tract, contaminated site (open / managed in place), low-lying area, bathtub model, LiDAR.
- **Source material:** `README.md` (Method, Limitations) and `brief/findings_brief.md`.
- **Done when:** every term in the list is there, no definition is longer than 2 sentences, and nothing contradicts the README.
- *(Cooper may reuse these as tooltip text in the viewer.)*

### H2. Presentation outline (7 slides)
- **Create:** `docs/presentation_outline.md`
- **What:** a 7-slide outline for the DataFest presentation. For each slide: a title, 2-4 bullets, the exact numbers to show (copied from `stats.json` / the brief), and 2-3 sentences of speaker notes.
- **Suggested slides:** (1) The problem: West Oakland and rising seas; (2) What official maps show (ART) vs. what we add; (3) Who floods: buildings and residents by scenario; (4) Cut off: Fire Station 2 and emergency access; (5) Contamination near flooding (say "proximity, not exposure"); (6) Where help should start: the top-priority tracts; (7) Limitations + live 3D demo.
- **Done when:** every number in the outline matches `stats.json` exactly. Add a line at the bottom listing which `stats.json` keys you used.

### H3. Spanish version of the key findings
- **Create:** `docs/brief_es.md`
- **What:** translate these parts of `brief/findings_brief.md` into clear, everyday Spanish: the title, the pitch line, "Key findings", the "Impacts by scenario" table (with header text translated and numbers unchanged), and "Limitations".
- **Done when:** all the numbers are identical to the English brief. List any term you weren't sure how to translate (for example "high-burden tract") at the bottom, so a fluent teammate can check it.

---

## Leo's agent: small checks and helper data

### L1. Sanity-check script for `stats.json`
- **Create:** `tests/check_stats.py` (plain Python, standard library only: just `json` and `assert`).
- **Checks to write:**
  1. `scenario_ids` is exactly `["0ft","1ft","2ft","3ft","4ft","5ft"]`, and `scenarios` has 6 entries in that order.
  2. `buildings_flooded`, `residents_affected` and `road_km_impassable` never decrease from one scenario to the next.
  3. Every `share_affected_high_burden` that isn't null is between 0 and 1.
  4. `top_priority["4ft"]` has at most 5 entries with ranks 1, 2, 3...
  5. Every scenario has the keys the viewer needs: `id, slr_ft, water_level_navd88_m, water_level_studs, buildings_flooded, residents_affected, facilities_lost, residents_cut_off, residents_degraded, contaminated_sites_near_flooding, road_km_impassable`.
- **Run:** `python tests/check_stats.py`. It prints `ALL CHECKS PASSED` or the first failure.
- **Done when:** it passes on the current `stats.json`. If a check fails, **don't change the data**: post the failure in the doc.

### L2. Viewpoints for the 3D viewer
- **Create:** `tools/make_viewpoints.py` and its output `roblox/viewpoints.json`.
- **What:** camera viewpoints for 6 places: West Oakland (around Mandela Pkwy and 7th St), Jack London Square, Port of Oakland (Middle Harbor), Oakland Fire Station 2 (47 Clay St), Prescott neighborhood, and Lake Merritt channel. For each, find the latitude/longitude (for example from openstreetmap.org) and convert it to the viewer's local frame:
  - transform lon/lat (EPSG:4326) to EPSG:26910 with `pyproj` (`Transformer.from_crs("EPSG:4326","EPSG:26910", always_xy=True)`),
  - `x = easting - 558520`, `z = -(northing - 4182723)` (meters; Z points south),
  - output `[{"name": ..., "lon": ..., "lat": ..., "x_m": ..., "z_m": ..., "look_height_m": 120}]`.
- **Done when:** all 6 points have `0 <= x_m <= 7076` and `-4492 <= z_m <= 0` (inside the study area), and the script runs with `.venv/bin/python tools/make_viewpoints.py`.

### L3. Check the README's data-source links + Windows run steps
- **Edit:** only the "Data sources" and "How to run" sections of `README.md`.
- **What:** (a) open each source link or service named in the Data sources table and note whether it still works; mark broken ones with "(link broken as of <date>)", and don't remove anything. (b) Under "How to run", add a short **Windows** version of the three setup commands (`py -3 -m venv .venv`, `.venv\Scripts\pip install -r requirements.txt`, and running the scripts in `pipeline/run_all.sh` order with `.venv\Scripts\python`).
- **Done when:** the table has a status for every row and the Windows steps are there. Don't touch any other README section (Kai's agent may be editing "Validation").

---

## If you finish early

Post in the doc's work log and ask for the next task. Don't start bigger work (pipeline changes, the Roblox viewer, the analysis tasks K1-K8) without checking with the owner first.
