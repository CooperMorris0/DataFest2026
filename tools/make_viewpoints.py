"""Generate camera viewpoints in the Roblox viewer's local coordinate frame."""

import json
from pathlib import Path

from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "roblox" / "viewpoints.json"
SW_EASTING_M = 558520
SW_NORTHING_M = 4182723
MAX_X_M = 7076
MIN_Z_M = -4492

# Coordinates were looked up in OpenStreetMap/Nominatim (2026-11-21); the two
# neighborhood viewpoints are representative street intersections.
PLACES = [
    {"name": "West Oakland (Mandela Pkwy & 7th St)", "lon": -122.2931, "lat": 37.8053},
    {"name": "Jack London Square", "lon": -122.2746851, "lat": 37.7957886},
    {"name": "Port of Oakland (Middle Harbor)", "lon": -122.3241804, "lat": 37.8032},
    {"name": "Oakland Fire Station 2 (47 Clay St)", "lon": -122.2795429, "lat": 37.7959773},
    {"name": "Prescott neighborhood", "lon": -122.2910, "lat": 37.8038},
    {"name": "Lake Merritt channel", "lon": -122.2606799, "lat": 37.7990453},
]


def main():
    project = Transformer.from_crs("EPSG:4326", "EPSG:26910", always_xy=True)
    viewpoints = []
    for place in PLACES:
        easting, northing = project.transform(place["lon"], place["lat"])
        x_m = easting - SW_EASTING_M
        z_m = -(northing - SW_NORTHING_M)
        assert 0 <= x_m <= MAX_X_M, f"{place['name']} falls outside east/west bounds: {x_m}"
        assert MIN_Z_M <= z_m <= 0, f"{place['name']} falls outside north/south bounds: {z_m}"
        viewpoints.append(
            {
                "name": place["name"],
                "lon": place["lon"],
                "lat": place["lat"],
                "x_m": round(x_m, 2),
                "z_m": round(z_m, 2),
                "look_height_m": 120,
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(viewpoints, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(viewpoints)} viewpoints to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
