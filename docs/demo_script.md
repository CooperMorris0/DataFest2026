# Demo script: Oakland Flood Consequence Explorer (about 4 minutes)

A click-by-click walkthrough of the Roblox world for the DataFest presentation. Every number below is copied from `data/processed/stats.json` and FloodWatch's outputs as of 2026-11-21. If the pipeline is rerun, recheck them against the sim's stats panel, which always reads `stats.json`.

**Before you start**
- Open the DataFest2026 place in Studio and press **Play**, or open the published experience.
- Use a projector-sized window. Close the Explorer and Properties panels.
- You start in the **Overview**, at **Today**, in **Flood** mode.
- Controls: WASD to move, Q/E for down/up, hold the right mouse button to look around, mouse wheel to change speed, **H** to hide the panels.
- Backup plan if Roblox misbehaves: `brief/findings_brief.md`, plus `data/processed/flood_4ft.png` and `isolation_5ft.png`.

---

### 0:00 · The hook (Overview, Today)
**Say:** "This is West Oakland, Jack London Square and the Port, built from 2021 LiDAR and 13,581 real buildings. Official maps from the state's ART program show *where* water goes. We show what it means for the people who live here."

### 0:30 · Water rises (Flood mode)
**Click** +1 ft → +2 ft → +3 ft. Let the bay rise between clicks.
- **Say at +3 ft:** "At 3 feet, 49 buildings flood and about 900 residents are affected. 96% of them live in the state's most pollution-burdened neighborhoods, the top quarter on CalEnviroScreen. That's 3.5 times their share of Oakland's population."
- Point out the **red roads**: 2.9 km of road are impassable (water deeper than 15 cm).

### 1:00 · Cut off (+4 ft, Cut off mode)
**Click** +4 ft, then **Cut off**, then the **Fire Station 2** viewpoint.
**Say:** "At 4 feet, only 117 buildings flood, but Oakland Fire Station 2 on the waterfront goes underwater. 217 residents are cut off from fire or medical help, and 235 more see response times more than double. Emergency access fails before most homes flood."

### 1:30 · Contamination (Contamination mode)
**Click** **Contamination**.
**Say:** "Thirty open or capped cleanup sites sit in or within 100 meters of the 4-foot flood. That's proximity, not proof that anyone is exposed. But it's where floodwater and old industrial land meet."

### 1:50 · Where help should start (Priority mode)
**Click** **Priority** and point at the list on the right.
**Say:** "We combine exposure with CalEnviroScreen vulnerability. At 4 feet, tract 4033.02 ranks first: 83rd percentile on CalEnviroScreen, 335 residents affected and 125 cut off."

### 2:10 · The 5-foot cliff (+5 ft)
**Click** **+5 ft*** and **Flood** mode, then **Overview**.
**Say:** "At about 5 feet, the flooding jumps: 1,137 buildings, about 7,700 residents, and 5,536 people cut off. The star means we use ART's 5½-foot map, because ART has no 5-foot map. That's the conservative choice."

### 2:40 · It already floods (FloodWatch mode)
**Click** **FloodWatch**. The columns rise; taller means more flood reports.
**Say:** "This is Kai's FloodWatch website, in 3D, block for block. It shows 1,521 storm-drain flood reports to 311 since 2013, today, from rain. And here's the twist: they're mostly *different places*. Only 47 blocks have both. West Oakland has two flood problems: overwhelmed storm drains in the neighborhoods now, and permanent flooding on the waterfront later."

### 3:10 · Walk it (walk mode)
1. **Click** **Jack London**, then **Walk here**. You land on Jefferson Street. Press **H** to hide the panels.
2. **Click** **Today**. The readout says *"Dry here."* Then **+4 ft**: *"Water here: about 0.3 m (1 ft), knee-deep"*. Then **+5 ft**: *"about 0.7 m, waist-deep"*. Walk a few steps: you're wading slowly. **Say:** "This is someone's street."
3. Optional: the readout's bottom line shows this block's FloodWatch risk and its flood reports to 311.

### 3:40 · Close
Press **H** to bring the panels back. **Say:** "Everything here comes from public data: ART, USGS, NOAA, CalEnviroScreen, the Census, and state cleanup databases. We built it as input to Oakland's 2026–27 shoreline adaptation plan. It's not an official hazard map, but it shows where help should start."

---

## If something goes wrong
- **Buttons do nothing:** a recolor is still running. Wait a second; each click recolors about 18,000 parts.
- **Fell through the world or stuck in a building:** click **Fly**, then **Walk here** again.
- **Numbers look different from this script:** the pipeline was rerun. Trust the stats panel, which reads `stats.json`.
- **Deep link from the FloodWatch website** (if the experience is published): `https://www.roblox.com/games/start?placeId=139477133252061&launchData=8928308146fffff` opens 6th Street, a Very high rain-risk block that stays dry at every sea-level scenario. It's a good example of the "two problems" point.
