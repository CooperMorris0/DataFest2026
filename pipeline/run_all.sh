#!/usr/bin/env bash
# Run the full pipeline in order. Downloads are cached in data/raw/ (never re-fetched).
set -euo pipefail
cd "$(dirname "$0")"
PY=../.venv/bin/python
for s in 01_fetch_osm 01b_fetch_landuse 01c_fetch_network_osm 01d_fetch_facilities \
         01e_fetch_tiger_roads 01f_fetch_contamination 01h_fetch_trees 02_fetch_hazard 03_fetch_elevation \
         04_building_heights 04b_alignment_check hazard_bathtub 05_flood_exposure \
         05b_validate_hazard 06_consequences 07_equity_priority 08_export_for_roblox 08b_export_roblox_world \
         09_findings_brief 10_floodwatch_slr 08c_import_floodwatch 08d_export_styled; do
  echo "=== $s"
  $PY "$s.py"
done
