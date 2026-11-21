-- ReplicatedStorage.FloodViewer.Config (ModuleScript)
-- Single source of shared constants for the Oakland Flood Consequence Explorer viewer.
-- Must match pipeline/config.py (STUDS_PER_METER, frame origin, scenario ids).
local Config = {}

Config.STUDS_PER_METER = 1 / 0.28      -- 1 stud = 0.28 m (pipeline/config.py)
Config.SERVER = "http://127.0.0.1:8770" -- python -m http.server 8770 --bind 127.0.0.1 (repo root)
Config.DATA = Config.SERVER .. "/data/processed/roblox"
Config.ORIGIN_EPSG26910 = { 558520, 4182723 } -- grid SW corner; X = east, Z = -north

Config.SCENARIOS = { "0ft", "1ft", "2ft", "3ft", "4ft", "5ft" }
Config.SCENARIO_LABELS = { "Today", "+1 ft", "+2 ft", "+3 ft", "+4 ft", "+5 ft*" }
Config.MHHW_M = 1.941                   -- NOAA 9414750 Alameda, NAVD88
Config.BUILDING_SINK_M = 1.0            -- sink buildings below their lowest ground point

Config.MODES = { "Flood", "Cut off", "Contamination", "Priority" }

Config.COLORS = {
	building = Color3.fromRGB(200, 200, 196),
	buildingDim = Color3.fromRGB(170, 170, 166),
	floodShallow = Color3.fromRGB(150, 200, 245),
	floodDeep = Color3.fromRGB(20, 55, 150),
	lowLying = Color3.fromRGB(120, 190, 120),
	cutOff = Color3.fromRGB(220, 40, 40),
	degraded = Color3.fromRGB(245, 150, 30),
	contam = Color3.fromRGB(150, 60, 190),
	priorityLow = Color3.fromRGB(255, 235, 140),
	priorityHigh = Color3.fromRGB(190, 20, 40),
	road = Color3.fromRGB(60, 60, 64),
	roadImpassable = Color3.fromRGB(230, 40, 40),
	water = Color3.fromRGB(40, 110, 190),
	inlandWater = Color3.fromRGB(50, 120, 170),
}

Config.FACILITY_COLORS = {
	fire_station = Color3.fromRGB(230, 50, 40),
	hospital = Color3.fromRGB(240, 240, 240),
	clinic = Color3.fromRGB(120, 220, 230),
	nursing_facility = Color3.fromRGB(240, 170, 220),
	school = Color3.fromRGB(250, 210, 60),
	rail_station = Color3.fromRGB(80, 160, 255),
}

Config.TERRAIN_MATERIALS = {
	Enum.Material.Pavement, Enum.Material.Asphalt, Enum.Material.Grass, Enum.Material.Mud, Enum.Material.Rock,
}

-- meters (local frame) -> studs
function Config.m(v)
	return v * Config.STUDS_PER_METER
end

return Config
