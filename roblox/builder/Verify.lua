-- ServerStorage.FloodBuilder.Verify (ModuleScript). Run after a FULL build.
--   print(require(game.ServerStorage.FloodBuilder.Verify).run())
-- Checks that per-scenario counts of building parts match stats.json exactly, and samples
-- terrain along transects to confirm the bay has a bed below the water surface.
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Config = require(ReplicatedStorage.FloodViewer.Config)

local Verify = {}

function Verify.run()
	local stats = HttpService:JSONDecode(require(ReplicatedStorage.FloodViewer.StatsJSON))
	local parts = {}
	for _, p in ipairs(workspace.City.Buildings:GetDescendants()) do
		-- main building parts only (styled roofs/storefronts are children without attributes)
		if p:IsA("BasePart") and p:GetAttribute("Flooded") then table.insert(parts, p) end
	end
	local lines = { ("buildings in place: %d (stats.json n_buildings = %d)"):format(#parts, stats.n_buildings) }
	local allOk = #parts == stats.n_buildings
	for i, s in ipairs(stats.scenarios) do
		local fl, cut = 0, 0
		for _, p in ipairs(parts) do
			if string.sub(p:GetAttribute("Flooded"), i, i) == "1" then fl += 1 end
			if string.sub(p:GetAttribute("Cut"), i, i) == "1" then cut += 1 end
		end
		local ok = fl == s.buildings_flooded and cut == s.buildings_cut_off
		allOk = allOk and ok
		table.insert(lines, ("%s flooded %d/%d cut %d/%d %s"):format(s.id, fl, s.buildings_flooded, cut,
			s.buildings_cut_off, ok and "OK" or "MISMATCH"))
	end
	-- water check: bay bed must be below the MHHW water surface at a few bay points
	-- the four verified open-water seed points from pipeline/config.py, in local meters
	local probes = { { 280, -1677 }, { 1080, -3278 }, { 2279, -327 }, { 4079, -177 } }
	for _, pr in ipairs(probes) do
		local origin = Vector3.new(Config.m(pr[1]), 600, Config.m(pr[2]))
		local params = RaycastParams.new()
		params.FilterDescendantsInstances = { workspace.Terrain }
		params.FilterType = Enum.RaycastFilterType.Include
		params.IgnoreWater = true -- measure the bay floor under the terrain water
		local hit = workspace:Raycast(origin, Vector3.new(0, -1200, 0), params)
		local y = hit and hit.Position.Y / Config.STUDS_PER_METER or nil
		table.insert(lines, ("bay probe (%d,%d) m: terrain at %s m (MHHW %.2f) %s"):format(pr[1], pr[2],
			y and ("%.2f"):format(y) or "none", Config.MHHW_M,
			(y and y < Config.MHHW_M) and "OK" or "CHECK"))
	end
	table.insert(lines, allOk and "COUNTS MATCH stats.json" or "COUNT MISMATCH")
	return table.concat(lines, "\n")
end

return Verify
