"""Generate the one-page planner brief (brief/findings_brief.md) from stats.json, so every
number in it matches the pipeline exactly."""
import json
import shutil

from config import PROC, ROOT

S = json.loads((PROC / "stats.json").read_text())
sc = {s["id"]: s for s in S["scenarios"]}
out = ROOT / "brief"
out.mkdir(exist_ok=True)
# map images from the pipeline
for name in ("isolation_5ft.png", "flood_4ft.png"):
    if (PROC / name).exists():
        shutil.copy(PROC / name, out / name)


def n(x):
    return f"{x:,}"


rows = []
for sid in S["scenario_ids"]:
    s = sc[sid]
    src = (f"ART {s['art_level_in']} in" + ("*" if s["art_level_in"] != 12 * s["slr_ft"] else "")) \
        if s["hazard_source"] == "ART" else "model"
    rows.append(f"| +{s['slr_ft']} ft | {src} | {n(s['buildings_flooded'])} | {n(s['residents_affected'])} | "
                f"{s['facilities_lost']} | {n(s['residents_cut_off'])} | {n(s['residents_degraded'])} | "
                f"{s['contaminated_sites_near_flooding']} | {s['road_km_impassable']:.1f} |")

base_oak = S["equity_baselines"]["oakland"]["share_high_burden"]


def top_table(sid):
    t = S["top_priority"][sid]
    lines = ["| # | Tract | City | CalEnviroScreen pctl | Flooded bldgs | Residents affected | Residents cut off | Slower response* |",
             "|---|---|---|---|---|---|---|---|"]
    for r in t:
        lines.append(f"| {r['rank']} | {r['tract_id'][-6:-2]}.{r['tract_id'][-2:]} | {r['city']} | {r['ces_pctl']:.0f} | "
                     f"{r['buildings_flooded']} | {n(r['residents_affected'])} | {n(r['residents_cut_off'])} | "
                     f"{n(r['residents_degraded'])} |")
    return "\n".join(lines)


def fac_line(sid):
    lst = sc[sid]["facilities_lost_list"]
    return ", ".join(f"{f['name']} ({f['type'].replace('_', ' ')})" for f in lst) or "none"


s3, s4, s5 = sc["3ft"], sc["4ft"], sc["5ft"]
br = {b["art_level_in"]: b for b in S["hazard"]["art_bracket_for_5ft"]}
md = f"""# West Oakland Flood Consequences: Findings Brief

*Input to Oakland's Subregional Shoreline Adaptation Plan community process (2026-2027). A
student-built exploration tool, **not an official hazard or evacuation assessment**. Defer to
ART, BCDC, and City of Oakland plans. Generated {S['generated']} from `stats.json`.*

**Official flood maps show where water goes. This shows what it means for the people who live there, and where help should start.**

## Key findings

1. **Exposure concentrates on already-burdened communities.** At +3 ft and +4 ft, about
   {s3['share_affected_high_burden']:.0%} and {s4['share_affected_high_burden']:.0%} of affected residents live in
   CalEnviroScreen top-quartile tracts, versus {base_oak:.0%} of Oakland residents overall
   ({s4['representation_ratio']['oakland']:.1f}x over-represented at +4 ft).
2. **Emergency access fails before homes flood.** At +4 ft, {n(s4['residents_cut_off'])} residents are cut off
   from fire or medical services and {n(s4['residents_degraded'])} more face at least doubled response times,
   largely because **{fac_line('4ft')}** floods. At +5 ft (ART 66 in): {n(s5['residents_cut_off'])} cut off.
3. **Contamination is close to the water.** {s4['contaminated_sites_near_flooding']} open or managed-in-place
   cleanup sites lie in or within 100 m of +4 ft flooding ({s5['contaminated_sites_near_flooding']} at +5 ft), with
   {n(s5['residents_near_flooded_contamination'])} residents nearby at +5 ft. *Proximity, not proof of exposure.*
4. **A hidden risk below the waterline.** At +4 ft, {n(s4['buildings_lowlying_only'])} more buildings sit below the
   water level but are protected by higher ground (ART "low-lying" areas). Groundwater rise
   and drainage failure, not modeled here, could make these the next to flood.

## Impacts by scenario

| Sea-level rise | Hazard | Buildings flooded | Residents affected | Facilities lost | Residents cut off | Residents degraded access | Contaminated sites near flooding | Impassable road km |
|---|---|---|---|---|---|---|---|---|
{chr(10).join(rows)}

\\* ART publishes no 60-inch layer, so the "+5 ft" row uses ART's **66-inch (+5.5 ft)** map, a
deliberately conservative choice. For reference, ART floods {n(br[52]['buildings_flooded'])} buildings at
+4.3 ft (52 in), and our LiDAR model floods {n(S['hazard']['bathtub_5ft_buildings'])} at exactly +5 ft.

## Where help should start: top priority tracts (+4 ft)

{top_table('4ft')}

\\*Residents whose fire or medical response time more than doubles (for example, because
Fire Station 2 floods at +4 ft).

Priority = Exposure x Vulnerability. Exposure averages the share of buildings flooded and the
share of residents losing emergency access (cut off, plus half weight for a doubled response
time), each scaled 0-1 across tracts. A flooded fire station or clinic counts through the
people it serves, not in its own tract.
Vulnerability is the CalEnviroScreen 4.0 percentile. Port/industrial tracts without a
CalEnviroScreen score are not ranked.

![Emergency access at +5 ft](isolation_5ft.png)

## Method (3 sentences)

Flood extents come from the ART Bay Shoreline Flood Explorer (BCDC) at 12-66 inches above
today's high tide, with depth estimated from 2021 USGS LiDAR. We intersected these with
13,600 buildings, the road network (routing to Oakland fire stations and CDPH-licensed
hospitals and clinics), and state cleanup-site databases. Residents are allocated from
2020 Census tracts to residential parcels and weighted by CalEnviroScreen 4.0.

## Limitations

- Exploration tool, not an official hazard or evacuation map. Still-water flooding only: no
  storm surge (a 100-year storm adds ~0.84 m), rainfall, groundwater rise, or compound events.
- Depth is estimated from LiDAR inside ART's extent. "+5 ft" is ART's 5.5 ft map. Residents per building are an
  area-based estimate. 97% of building heights are estimated.
- Drive times are free-flow estimates without traffic or dispatch time. Fire stations include
  neighboring departments (Alameda, Emeryville/ACFD, Piedmont).
- Contaminated-site proximity does not mean residents are exposed.
"""
(out / "findings_brief.md").write_text(md)
print(f"wrote {out / 'findings_brief.md'} ({len(md.split())} words)")
