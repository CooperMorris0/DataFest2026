-- ServerStorage.FloodBuilder.Build (ModuleScript). Run once in EDIT mode, then save.
--   local Build = require(game.ServerStorage.FloodBuilder.Build)
--   task.spawn(Build.run, {sub = true})   -- small Jack London test area first
--   task.spawn(Build.run, {})             -- full study area
-- Progress: workspace.City:GetAttribute("Progress"). Resume-aware: rerunning skips
-- finished terrain tiles and building/road shards.
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Config = require(ReplicatedStorage.FloodViewer.Config)
local DataLoader = require(script.Parent.DataLoader)
local TerrainWriter = require(script.Parent.TerrainWriter)
local WorldBuilder = require(script.Parent.WorldBuilder)
local StyledBuilder = require(script.Parent.StyledBuilder)

local Build = {}

-- Jack London Square test area: x 3900-5300 m, z -1100..0 m (local frame)
local SUB = { xm = { 3900, 5300 }, zm = { -1100, 0 } }

local function subShards()
	-- 1 km cells overlapping the sub-area
	local set = {}
	for i = math.floor(SUB.xm[1] / 1000), math.floor(SUB.xm[2] / 1000) do
		for j = math.floor(-SUB.zm[2] / 1000), math.floor(-SUB.zm[1] / 1000) do
			set[("cell_%d_%d"):format(i, j)] = true
		end
	end
	return set
end

local function subTiles(meta)
	local cell = meta.tile_cols * meta.voxel_studs / Config.STUDS_PER_METER -- m per tile
	return {
		math.floor(SUB.xm[1] / cell), math.floor(SUB.xm[2] / cell),
		math.floor(-SUB.zm[2] / cell), math.floor(-SUB.zm[1] / cell),
	}
end

local function writeStatsModule()
	-- Bake stats.json into a ModuleScript so play mode never needs HTTP.
	local json = DataLoader.get(Config.SERVER .. "/data/processed/stats.json")
	local fv = ReplicatedStorage.FloodViewer
	-- always a fresh instance: require() caches a ModuleScript's first result per session
	if fv:FindFirstChild("StatsJSON") then fv.StatsJSON:Destroy() end
	local mod = Instance.new("ModuleScript")
	mod.Name = "StatsJSON"
	mod.Source = "-- generated from data/processed/stats.json by FloodBuilder.Build; do not edit\nreturn [==[" .. json .. "]==]\n"
	mod.Parent = fv
	return HttpService:JSONDecode(json)
end

local function setupPlace(stats)
	workspace.StreamingEnabled = false -- ~30k parts; recoloring needs all of them on the client
	local base = workspace:FindFirstChild("Baseplate")
	if base then base.Parent = game:GetService("ServerStorage") end -- keep, don't delete
	local L = game:GetService("Lighting")
	L.ClockTime = 13
	L.GeographicLatitude = 37.8
	local a = L:FindFirstChildOfClass("Atmosphere") or Instance.new("Atmosphere")
	a.Density = 0.08 -- light haze only: the study area is ~25,000 studs across
	a.Haze = 0.3
	a.Glare = 0
	a.Parent = L
	-- spawn for walk mode: Jack London Square
	local spawn = workspace:FindFirstChild("FloodSpawn") or Instance.new("SpawnLocation")
	spawn.Name = "FloodSpawn"
	spawn.Anchored = true
	spawn.Size = Vector3.new(12, 1, 12)
	spawn.Transparency = 1
	spawn.CanCollide = false
	spawn.Position = Vector3.new(Config.m(4600), Config.m(4) + 3, Config.m(-420))
	spawn.Parent = workspace
end

function Build.run(opts)
	opts = opts or {}
	local city = workspace:FindFirstChild("City") or Instance.new("Folder")
	city.Name = "City"
	city.Parent = workspace
	local ok, err = pcall(function()
		city:SetAttribute("Progress", "starting")
		local stats = writeStatsModule()
		setupPlace(stats)
		local manifest = DataLoader.json("manifest.json")
		local levels = {}
		for i, s in ipairs(stats.scenarios) do levels[i] = s.water_level_navd88_m end
		if not opts.skipTerrain then
			TerrainWriter.run(manifest.terrain_tiles, city, opts.sub and subTiles(manifest.terrain_tiles) or nil)
		end
		local filter = opts.sub and subShards() or nil
		WorldBuilder.buildings(manifest, city, filter)
		WorldBuilder.roads(manifest, city, filter)
		WorldBuilder.water(manifest, city, levels)
		WorldBuilder.markers(manifest, city)
		WorldBuilder.floodwatch(city)
		city:SetAttribute("BuiltSub", opts.sub == true)
		city:SetAttribute("Progress", "done")
	end)
	if not ok then
		city:SetAttribute("Progress", "ERROR: " .. tostring(err))
		warn("[Build] " .. tostring(err))
	end
end

-- Upgrade an already-built place in place (no terrain rewrite): solid buildings, street
-- names on roads (roads rebuilt), water detectable by raycasts, FloodWatch layer.
function Build.upgrade()
	local city = workspace.City
	city:SetAttribute("Progress", "upgrade: buildings")
	for n, p in ipairs(city.Buildings:GetDescendants()) do
		if p:IsA("BasePart") then p.CanCollide = true end
		if n % 3000 == 0 then task.wait() end
	end
	for n, p in ipairs(city.Water:GetDescendants()) do
		if p:IsA("BasePart") then p.CanQuery = true end
		if n % 3000 == 0 then task.wait() end
	end
	city:SetAttribute("Progress", "upgrade: roads")
	city.Roads:Destroy()
	local manifest = DataLoader.json("manifest.json")
	WorldBuilder.roads(manifest, city)
	city:SetAttribute("Progress", "upgrade: floodwatch")
	writeStatsModule()
	WorldBuilder.floodwatch(city)
	city:SetAttribute("Progress", "done")
end

-- Replace the plain boxes with the styled city (textured walls, roofs, storefronts, roads with
-- markings + sidewalks, street/park trees), then re-tag FloodWatch blocks and set the look.
-- Terrain, water parts, markers and FloodWatch layers are kept. Resume-aware per shard.
function Build.restyle(opts)
	opts = opts or {}
	local city = workspace.City
	local ok, err = pcall(function()
		local manifest = DataLoader.json("manifest.json")
		StyledBuilder.setup(manifest)
		if not city:GetAttribute("Styled") then
			for _, name in ipairs({ "Buildings", "Roads", "Trees" }) do
				if city:FindFirstChild(name) then city[name]:Destroy() end
			end
			city:SetAttribute("Styled", true)
		end
		StyledBuilder.build(manifest, city, "buildings")
		StyledBuilder.build(manifest, city, "roads")
		StyledBuilder.build(manifest, city, "trees")
		city:SetAttribute("Progress", "restyle: floodwatch")
		WorldBuilder.floodwatch(city)
		if not opts.skipEnvironment then
			city:SetAttribute("Progress", "restyle: environment")
			StyledBuilder.environment(manifest)
		end
		city:SetAttribute("Progress", "done")
	end)
	if not ok then
		city:SetAttribute("Progress", "ERROR: " .. tostring(err))
		warn("[Build.restyle] " .. tostring(err))
	end
end

return Build
