# Demo script: FloodWatch website (about 4 minutes)

A click-by-click walkthrough of the FloodWatch website for the DataFest presentation. The numbers come from `data/processed/stats.json`, `data/processed/floodwatch/services_summary.json`, `storm_prep_summary.json` and the FloodWatch README, as of 2026-11-21. If a pipeline step is rerun, recheck them there.

**Before you start**
- Open `oakland-flood-vulnerability/outputs/flood_vulnerability_map.html` in a browser (or the hosted copy, if the team publishes one). Address search uses Esri's geocoder, so you need internet.
- Use a projector-sized window. The map starts on all of Oakland, slider at **Today**.
- Backup plan if the site misbehaves: `brief/findings_brief.md`, plus `data/processed/flood_4ft.png`, `isolation_5ft.png` and `oakland-flood-vulnerability/outputs/services_today.png`.

---

### 0:00 · The hook (whole city, Today)
**Say:** "Official flood maps show where water goes. This map shows what flooding means for the people who live in Oakland, today and as the Bay rises, and where help should start."

### 0:20 · It already floods (Today)
Hover the red and dark-red hexagons in East Oakland and downtown.
**Say:** "Each hexagon is a block area. Risk combines about 6,200 flood reports to 311, a flood model, FEMA zones and social vulnerability, weighted by what a flood would disrupt: hospitals, main roads, bus stops, groceries."
- Point at **Where to act first**: Fruitvale Ave, International Blvd, 35th Ave, Hegenberger Rd and downtown/Chinatown.

### 1:00 · The services people can't do without
Turn on the community service markers.
**Say:** "If services were spread evenly, about 30% would be in high-risk areas. Instead it's 16 of 17 Head Start sites, 14 of 18 nursing homes and 6 of 8 BART stations."

### 1:30 · The Bay rises (slider)
Drag the slider from **Today** to +3 ft, then +5 ft.
**Say at +3 ft:** "Three feet is roughly what a 100-year storm tide floods temporarily today. East Oakland's shoreline, at the Coliseum, Hegenberger and the airport, is overtopped."
**Say at +5 ft:** "By 2100, under the state's higher scenarios, this is permanent. We use the state's ART maps; at 5 feet we use ART's 5½-foot map, the conservative choice."

### 2:10 · One address (search)
Type **47 Clay St, Oakland** (Oakland Fire Station 2, Jack London waterfront) and press Enter.
**Say:** "This is the fire station for the waterfront. It floods from +4 feet. At 4 feet only 117 buildings in West Oakland flood, but losing this station means 217 residents are cut off from fire or medical help and 235 more see response times more than double. Emergency access fails before most homes flood."
- Scroll to **What you can do**: adopt a drain, report to 311, flood insurance, a no-car evacuation plan.

### 2:50 · Two different problems
**Say:** "Here's the twist. In West Oakland, rain flooding and sea-level flooding are mostly different places: only 47 blocks have both. Overwhelmed storm drains in the neighborhoods now, permanent flooding on the waterfront later. Plans need both."
- Equity line: "At 3 and 4 feet, 94 to 96% of the affected residents live in the state's most pollution-burdened neighborhoods, 3.4 times their share of Oakland."

### 3:20 · What to do before the next storm (Storm prep)
Click the link to the **Storm prep** page and show **Shelters**.
**Say:** "Before the next storm: where people can go. Only 48 of 172 candidate shelters are on safe ground. About 142,000 people in high-risk areas have no safe site within walking distance. That's the case for resilience hubs in the flatlands."

### 3:50 · Close
**Say:** "Everything here is public data: ART, USGS, NOAA, FEMA, CDC, CalEnviroScreen, the Census and city 311 records. It's not an official hazard map, but it shows where help should start."

---

## If something goes wrong
- **Address search finds nothing:** pick a suggestion from the list, or click the hexagon at Jack London Square.
- **Numbers look different from this script:** a pipeline step was rerun. Trust `stats.json` and the FloodWatch summaries.
