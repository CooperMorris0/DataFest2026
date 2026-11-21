#!/usr/bin/env bash
# Run the full data pipeline in order. Downloads are cached in data/raw/.
set -euo pipefail
cd "$(dirname "$0")"
PY=../.venv/bin/python
for s in 01_fetch_osm 01b_fetch_landuse 02_fetch_elevation 03_building_heights 03b_alignment_check \
         04_flood_model 04b_validate_noaa 05_equity_overlay; do
  echo "=== $s"
  $PY "$s.py"
done
