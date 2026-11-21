# Slides outline: Oakland flooding, today and tomorrow

*Full-project outline for the DataFest 2026 presentation (draft, 2026-11-21). Covers the sea-level-rise pipeline,
FloodWatch, public services, storm prep and the Roblox demo. About 8½ minutes plus Q&A; trim slides marked
**(optional)** for a shorter slot. Henry's H2 (7-slide sea-level-rise outline) can reuse or trim this.*

**Numbers rule:** every number below is copied from `data/processed/stats.json`, the FloodWatch outputs
(`oakland-flood-vulnerability/README.md`, `data/processed/floodwatch/*_summary.json`) or the K1 results, as of
main `5d0a3a9`. If the pipeline is re-run, recheck them before presenting. The source key is in brackets after each number.

**Story in one line:** Oakland has two flood problems: overwhelmed storm drains that flood neighborhoods today,
and rising seas that will cut off the waterfront tomorrow. Both hit the same people hardest, and we can show
where help should start.

---

## 1. Title: "Two floods, one city"
- Oakland flooding, today and tomorrow
- Team names; DataFest 2026
- **Visual:** full-bleed screenshot of the Roblox world at +4 ft, or the FloodWatch map.
- **Speaker notes:** "On November 18, Oakland got 1.5 to 3 inches of rain, and streets in West Oakland and
  downtown flooded. Over the next 8 minutes we'll show where Oakland floods today, where it will flood as the
  Bay rises, and where help should start."
- *Time: 0:20*

## 2. The problem: official maps miss most of it
- FEMA's flood maps cover the shoreline and creeks, but most reported flooding is street flooding from storm drains.
- Blocks inside FEMA's 100-year floodplain average **1.2** flood reports to 311; blocks outside average **4.6**
  [FloodWatch notebook, section 7 results].
- Sea-level-rise maps (ART) show *where water goes*, not what it means for people.
- **Visual:** FloodWatch map with the FEMA 100-year floodplain outlined (it barely overlaps the red blocks).
- **Speaker notes:** "Official flood maps answer 'where does water go?' We asked 'what does it mean for the people
  who live there, and where should help start?'"
- *Time: 0:40*

## 3. What we built (one picture)
- **FloodWatch:** a block-by-block flood risk map for all of Oakland, from about **6,200** 311 flood reports
  (2013 to Nov 2026), elevation, FEMA zones and the CDC Social Vulnerability Index [FloodWatch README].
- **Sea-level-rise consequences:** West Oakland, Jack London and the Port at +1 to +5 ft, built on official ART
  flood maps, 2021 LiDAR and **13,581** buildings [stats.json n_buildings].
- **3D Roblox world:** walk your own street as the water rises.
- **Storm prep:** where people in high-risk areas can go (shelter sites on safe ground).
- **Visual:** four-panel diagram: data → FloodWatch + sea-level-rise pipeline → website + Roblox → actions.
- *Time: 0:30*

## 4. Today: where Oakland already floods
- Model trained on 311 reports predicts which blocks flood, tested on neighborhoods it never saw:
  ROC AUC **0.84** [FloodWatch spatial cross-validation].
- Backtest on the Dec 2022 to Jan 2023 atmospheric river storms: trained only on earlier data, checking the top
  **30%** of blocks would have caught **53%** of the blocks that flooded [FloodWatch backtest].
- Highest risk: East Oakland's flatlands (around Fruitvale to the Coliseum) and parts of West Oakland and downtown.
- **Visual:** `oakland-flood-vulnerability/outputs/fvi_maps.png` (hazard / vulnerability / index), or a
  screenshot of the website.
- **Speaker notes:** "Risk is high only where a block is both likely to flood *and* home to people who would
  struggle most to cope." Mention that report counts depend partly on who calls 311; the model flags blocks that
  look flood-prone but have no reports.
- *Time: 0:45*

## 5. Who it hits: the services people can't do without
- With an even spread, about **30%** of each type would sit in the highest-risk areas. Instead
  [services_summary.json, people-only flood × vulnerability score]:
  - **16 of 17** Head Start sites
  - **14 of 18** nursing homes
  - **6 of 8** BART stations
  - **7 of 11** dialysis clinics
- Worst cluster: downtown and Chinatown around 9th–12th Streets (36–51 flood reports within two blocks of
  Lincoln Elementary, Lincoln Square Rec Center, the Asian Branch library and a Head Start site).
- **Visual:** `oakland-flood-vulnerability/outputs/services_today.png` (bar chart with the 30% line).
- *Time: 0:40*

## 6. Tomorrow: as the Bay rises (West Oakland)
| Sea-level rise | Buildings flooded | Residents affected | Residents cut off |
|---|---|---|---|
| +3 ft | 49 | 907 | 71 |
| +4 ft | 117 | 1,341 | 217 |
| +5 ft* | 1,137 | 7,689 | 5,536 |

[stats.json scenarios]. \*"+5 ft" uses ART's 66-inch (5.5 ft) map, the conservative choice; ART has no 60-inch map.
- At +4 ft, **94%** of affected residents live in the state's most pollution-burdened tracts (CalEnviroScreen top
  quarter), versus **28%** of Oakland residents: **3.4x** over-represented
  [stats.json share_affected_high_burden, representation_ratio.oakland = 3.43].
- **Visual:** `brief/flood_4ft.png`, or the Roblox world at +4 ft.
- **Speaker notes:** "Little floods until about 3 feet. Then it climbs fast, and it lands on the same
  neighborhoods that already carry the most pollution."
- *Time: 0:50*

## 7. Emergency access fails before homes flood
- At +4 ft, only 117 buildings flood, but **Oakland Fire Station 2** on the Jack London waterfront goes under.
- **217** residents are cut off from fire or medical help, and **235** more see response times more than double
  [stats.json 4ft residents_cut_off, residents_degraded].
- At +5 ft, no other service building floods, but 11 West Oakland services lose at least 10% of the streets
  within a 5-minute walk, led by deFremery Pool (48%), Fire Station 2 and West Oakland BART (37%)
  [services.csv streets_impassable_5ft].
- **Visual:** `brief/isolation_5ft.png`, or `outputs/services_slr.png`.
- *Time: 0:40*

## 8. (optional) Contamination and hidden risk
- At +4 ft, **30** open or capped cleanup sites sit in or within 100 m of flooding (**110** at +5 ft)
  [stats.json contaminated_sites_near_flooding]. *Proximity, not proof of exposure.*
- At +4 ft, **422** more buildings sit below the water level behind higher ground (ART "low-lying")
  [stats.json buildings_lowlying_only]. Rising groundwater could reach them first.
- *Time: 0:30*

## 9. Two different flood problems
- Today's rain flooding and tomorrow's sea-level-rise flooding mostly hit **different places**: only **47**
  blocks have both at +5 ft [K1, hex_slr.csv].
- Sea-level rise floods the Port and shoreline first; storm-drain flooding is inland, in the neighborhoods.
- So both need plans: drains and neighborhood help now, shoreline and access planning for later.
- **Visual:** `oakland-flood-vulnerability/outputs/k1_today_vs_slr.png` (three maps side by side).
- *Time: 0:30*

## 10. Live demo: walk it (Roblox)
- Follow `docs/demo_script.md`, shortened:
  1. Overview, Flood mode: click +3 → +4 → +5 ft.
  2. **Fire Station 2** viewpoint in Cut off mode.
  3. FloodWatch mode: the columns show today's 311 reports.
  4. **Walk here** at Jack London (Jefferson St): "Dry here" today, knee-deep at +4 ft, waist-deep at +5 ft.
- **Backup** if Roblox misbehaves: the FloodWatch website and `brief/findings_brief.md` screenshots.
- *Time: 1:30*

## 11. Where help should start
- **Storm prep list:** all **13,058** city storm drain inlets ranked by flood history, flood likelihood and who
  lives nearby. The top 25 crew stops have **322** flood reports within 100 m, mostly in East Oakland
  (62nd–66th Avenues) and Chinatown [storm_prep_summary.json].
- **Shelters:** only **48 of 172** libraries, rec centers, senior centers and schools are on safe ground. The 12
  best sites reach **38%** of residents of high-risk areas within a 15-minute walk; **289** high-risk blocks
  (about **142,000** residents) have none in walking distance [storm_prep_summary.json].
- **Priority tract at +4 ft:** 4033.02 (CalEnviroScreen 83rd percentile; 335 residents affected, 125 cut off)
  [stats.json top_priority].
- **Visual:** screenshot of `outputs/storm_prep_map.html` (drains tab, then shelters tab with the purple gaps).
- *Time: 0:50*

## 12. What Oakland could do, and limits
- **Now:** clear the top-ranked drains before forecast storms; recruit Adopt-a-Drain volunteers in high-risk
  blocks; set up resilience hubs on safe ground in the flatlands; multilingual storm alerts.
- **Next:** raise or relocate Fire Station 2; tide gates on storm outfalls; raise key access streets around
  West Oakland BART; feed this into Oakland's 2026–27 Shoreline Adaptation Plan.
- **Limits:** a student exploration tool, not an official hazard or evacuation map. Still water only (no storm
  surge, rain or groundwater in the sea-level-rise model); residents and depths are estimates; 311 reports
  depend on who calls; some site locations come from 2013 city data.
- **Close:** "Official maps show where water goes. We show what it means for the people who live there, and
  where help should start." Then Q&A.
- *Time: 0:45*

---

## Backup slides (for questions)
- **B1. Method details:** FloodWatch features and model; sea-level-rise pipeline steps (ART extents, LiDAR depth,
  routing to fire and medical services, CalEnviroScreen weighting). See `README.md` and the FloodWatch README.
- **B2. Validation:** ART vs our bathtub model and vs NOAA (README "Validation"); FloodWatch backtest; K1 hex sums
  match `stats.json` exactly.
- **B3. Full impacts table:** the scenario table from `brief/findings_brief.md`.
- **B4. Data sources:** section 17 of the team doc and the README data-sources table.
- **B5. Why "+5 ft" is ART 66 in:** ART has no 60-inch map; ART 52 in floods 620 buildings, our LiDAR model at
  exactly 5 ft floods 417 [brief footnote].

## Open items before presenting
- Assign a presenter to each slide (suggested split: Kai 2–5, 9, 11; Cooper 6–8, 10; Henry and Leo 1, 12).
- Recheck numbers if any pipeline step is re-run.
- Confirm the Roblox demo machine and a backup.
- Decide between the 12-slide version and a shorter cut (drop 8, merge 9 into 10).
