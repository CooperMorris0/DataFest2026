# Roblox viewer setup

The 3D world is **built once in Edit mode and saved in the place**. In play mode the scripts only recolor parts, move water and show stats. They never use HTTP and never recompute floods.

## Where each script goes

| File | Studio location | Type |
|---|---|---|
| `roblox/Config.lua` | `ReplicatedStorage.FloodViewer.Config` | ModuleScript |
| *(generated)* | `ReplicatedStorage.FloodViewer.StatsJSON` | ModuleScript holding `stats.json` (written by the builder) |
| `roblox/builder/DataLoader.lua` | `ServerStorage.FloodBuilder.DataLoader` | ModuleScript |
| `roblox/builder/TerrainWriter.lua` | `ServerStorage.FloodBuilder.TerrainWriter` | ModuleScript |
| `roblox/builder/WorldBuilder.lua` | `ServerStorage.FloodBuilder.WorldBuilder` | ModuleScript |
| `roblox/builder/Build.lua` | `ServerStorage.FloodBuilder.Build` | ModuleScript |
| `roblox/builder/Verify.lua` | `ServerStorage.FloodBuilder.Verify` | ModuleScript |
| `roblox/client/FloodClient.client.lua` | `StarterPlayer.StarterPlayerScripts.FloodClient` | LocalScript |

`roblox/sync.json` lists the same mapping. An agent with the Roblox Studio MCP can sync all the files in one step (see "Sync with an agent" below).

## Build the world

1. Run the data pipeline (`pipeline/run_all.sh`). It must include `08_export_for_roblox` and `08b_export_roblox_world`.
2. Serve the repo root locally (keep this terminal open during the build):
   ```bash
   .venv/bin/python -m http.server 8770 --bind 127.0.0.1
   ```
3. Let Studio reach the server, using one of these:
   - **By hand (command bar):** Game Settings → Security → *Allow HTTP Requests* = on.
   - **Over MCP:** Assistant Settings → MCP Permissions → *Connect to the internet* → add `127.0.0.1:8770` to the HTTP domain allow list.
4. Put the scripts in place (table above).
5. Test on the small Jack London area first. In the command bar:
   ```lua
   task.spawn(require(game.ServerStorage.FloodBuilder.Build).run, {sub = true})
   ```
   Watch `workspace.City`'s **Progress** attribute.
6. Build everything. Rerunning is safe, because finished terrain tiles and shards are skipped:
   ```lua
   task.spawn(require(game.ServerStorage.FloodBuilder.Build).run, {})
   ```
   Terrain takes the longest: 1,600 tiles of 128 × 128 voxel columns.
7. Verify. The counts must match `stats.json` exactly:
   ```lua
   print(require(game.ServerStorage.FloodBuilder.Verify).run())
   ```
8. **Save** (File → Save). Also export a backup to `backups/oakland_<step>_<time>.rbxl`, which is gitignored.

You can turn *Allow HTTP Requests* back off after the build, because play mode doesn't need it.

## Controls (play mode)

- **Scenario buttons** (Today, +1 … +5 ft): raise the water and recolor everything.
- **Map modes:** Flood / Cut off / Contamination / Priority, each with its own legend.
- **Fly camera:** WASD to move, Q/E for down/up, hold the right mouse button to look around, mouse wheel to change speed, Shift for ×5 speed.
- **Viewpoints:** Overview, West Oakland, Jack London, Port, Fire Station 2. **Walk here** drops your avatar at the current spot.
- **Click a building** to see its estimated depth, emergency access, height and tract.

## Sync with an agent (Roblox Studio MCP)

With the server running and `127.0.0.1:8770` allowlisted, run this through `execute_luau`. It fetches each file in `sync.json` and creates or updates the script:

```lua
local HS = game:GetService("HttpService")
local base = "http://127.0.0.1:8770/"
for _, e in ipairs(HS:JSONDecode(HS:GetAsync(base .. "roblox/sync.json", true))) do
	local parent = game
	local parts = string.split(e.path, ".")
	for i = 1, #parts - 1 do
		parent = parent:FindFirstChild(parts[i]) or (i == 1 and game:GetService(parts[i])) or (function()
			local f = Instance.new("Folder"); f.Name = parts[i]; f.Parent = parent; return f end)()
	end
	local s = parent:FindFirstChild(parts[#parts]) or Instance.new(e.class)
	s.Name = parts[#parts]
	s.Source = HS:GetAsync(base .. e.file, true)
	s.Parent = parent
end
```

## Notes

- Scale: 1 stud = 0.28 m (`Config.STUDS_PER_METER`, the same value as `pipeline/config.py`). Origin = study-area SW corner. X = east, Z = −north. Elevations are NAVD88.
- Water: the open bay rises to each scenario's level. Each scenario's flood rectangles are pre-built and shown or hidden, so water appears only where the hazard data says it floods.
- `StreamingEnabled` is turned off by the builder, so the client can recolor every building (about 30k parts in total).
