"""Sanity checks for the viewer-facing stats export."""

import json


STATS_PATH = "data/processed/stats.json"
EXPECTED_SCENARIOS = ["0ft", "1ft", "2ft", "3ft", "4ft", "5ft"]
VIEWER_FIELDS = {
    "id",
    "slr_ft",
    "water_level_navd88_m",
    "water_level_studs",
    "buildings_flooded",
    "residents_affected",
    "facilities_lost",
    "residents_cut_off",
    "residents_degraded",
    "contaminated_sites_near_flooding",
    "road_km_impassable",
}


def main():
    with open(STATS_PATH, encoding="utf-8") as stats_file:
        stats = json.load(stats_file)

    assert stats["scenario_ids"] == EXPECTED_SCENARIOS, "scenario_ids must be 0ft through 5ft"
    scenarios = stats["scenarios"]
    assert len(scenarios) == 6, "scenarios must contain six entries"
    assert [scenario["id"] for scenario in scenarios] == EXPECTED_SCENARIOS, (
        "scenarios must be ordered 0ft through 5ft"
    )

    for field in ("buildings_flooded", "residents_affected", "road_km_impassable"):
        values = [scenario[field] for scenario in scenarios]
        assert all(earlier <= later for earlier, later in zip(values, values[1:])), (
            f"{field} must not decrease across scenarios: {values}"
        )

    for scenario in scenarios:
        share = scenario["share_affected_high_burden"]
        assert share is None or 0 <= share <= 1, (
            f"{scenario['id']} share_affected_high_burden must be null or between 0 and 1"
        )
        missing = VIEWER_FIELDS - scenario.keys()
        assert not missing, f"{scenario['id']} is missing viewer fields: {sorted(missing)}"

    top_priority = stats["top_priority"]["4ft"]
    assert len(top_priority) <= 5, "top_priority['4ft'] must contain at most five entries"
    assert [item["rank"] for item in top_priority] == list(range(1, len(top_priority) + 1)), (
        "top_priority['4ft'] ranks must start at 1 and increase without gaps"
    )

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
