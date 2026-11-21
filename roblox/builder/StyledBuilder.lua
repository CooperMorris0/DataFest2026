-- ServerStorage.FloodBuilder.StyledBuilder (ModuleScript). Edit-mode build only.
-- Builds the styled city from the primitive lists written by pipeline/08d_export_styled.py
-- (the same lists tools/blender_preview.py renders). Textures come from roblox/texture_assets.json
-- (uploaded once; asset ids logged there) as MaterialVariants, road Textures and leaf Decals.
local HttpService = game:GetService("HttpService")
local MaterialService = game:GetService("MaterialService")
local Config = require(game:GetService("ReplicatedStorage").FloodViewer.Config)
local DataLoader = require(script.Parent.DataLoader)

local StyledBuilder = {}
local SPM = Config.STUDS_PER_METER
local assets, looks

local function folder(parent, name)
	local f = parent:FindFirstChild(name)
	if not f then f = Instance.new("Folder"); f.Name = name; f.Parent = parent end
	return f
end

function StyledBuilder.setup(manifest)
	assets = HttpService:JSONDecode(DataLoader.get(Config.SERVER .. "/roblox/texture_assets.json"))
	looks = manifest.styled.looks
	for key, lk in pairs(looks) do
		local name = "FV_" .. key
		local mv = MaterialService:FindFirstChild(name) or Instance.new("MaterialVariant")
		mv.Name = name
		mv.BaseMaterial = Enum.Material[lk.base]
		mv.ColorMap = assets[lk.texture]
		if assets[lk.texture .. "_n"] then mv.NormalMap = assets[lk.texture .. "_n"] end
		mv.StudsPerTile = lk.tile_m * SPM
		mv.MaterialPattern = Enum.MaterialPattern.Regular
		mv.Parent = MaterialService
	end
	return assets
end

local SHAPES = { B = "Part", W = "WedgePart", C = "Part", K = "Part" }

local function rgb(c) return Color3.fromRGB(c[1], c[2], c[3]) end

function StyledBuilder.prim(p)
	local part = Instance.new(SHAPES[p.s])
	if p.s == "C" then part.Shape = Enum.PartType.Cylinder end
	part.Anchored = true
	part.CanTouch = false
	part.CanCollide = not p.nc
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.Size = Vector3.new(p.z[1], p.z[2], p.z[3])
	part.CFrame = CFrame.new(p.p[1], p.p[2], p.p[3])
		* CFrame.Angles(math.rad(p.r[1]), math.rad(p.r[2]), math.rad(p.r[3]))
	part.Color = rgb(p.c)
	local lk = looks[p.m]
	if lk then
		part.Material = Enum.Material[lk.base]
		part.MaterialVariant = "FV_" .. p.m
	else
		part.Material = Enum.Material[p.m] or Enum.Material.SmoothPlastic
	end
	if p.t then part.Transparency = p.t end
	if p.role == "leaf" or p.role == "road" or p.role == "sidewalk" then part.CastShadow = false end
	if p.s == "K" then -- leaf card: decal (alpha foliage) on both faces, tinted by species color
		part.CanQuery = false
		for _, face in ipairs({ Enum.NormalId.Front, Enum.NormalId.Back }) do
			local d = Instance.new("Decal")
			d.Texture = assets[p.d]
			d.Face = face
			d.Color3 = rgb(p.c)
			d.Parent = part
		end
	end
	if p.mk then -- painted lane markings on the road surface
		local t = Instance.new("Texture")
		t.Texture = assets["road_" .. p.mk .. "lane"]
		t.Face = Enum.NormalId.Top
		t.StudsPerTileU = p.z[1]
		t.StudsPerTileV = 12
		t.Parent = part
	end
	part:SetAttribute("BaseColor", part.Color)
	return part
end

local function setAttrs(part, a)
	for k, v in pairs(a) do
		if k == "BaseColor" then
			part:SetAttribute("BaseColor", rgb(v))
		elseif k ~= "id" then
			part:SetAttribute(k, v)
		end
	end
end

-- kind = "buildings" | "roads" | "trees"; resume-aware per shard (Done attribute)
function StyledBuilder.build(manifest, city, kind)
	local root = folder(city, kind == "buildings" and "Buildings" or kind == "roads" and "Roads" or "Trees")
	local list = manifest.styled[kind]
	for n, path in ipairs(list) do
		local cell = path:match("cell_[%-%d_]+")
		local f = root:FindFirstChild(cell)
		if not (f and f:GetAttribute("Done")) then
			if f then f:Destroy() end
			local staging = Instance.new("Folder")
			staging.Name = cell
			local data = DataLoader.json(path)
			if kind == "trees" then
				for _, p in ipairs(data) do StyledBuilder.prim(p).Parent = staging end
			else
				for _, e in ipairs(data) do
					local main = StyledBuilder.prim(e.p[1])
					setAttrs(main, e.a)
					if kind == "buildings" then
						main.Name = tostring(e.a.id)
						main.CanQuery = true
					else
						main.Name = "road"
					end
					for i = 2, #e.p do
						local child = StyledBuilder.prim(e.p[i])
						child.CanQuery = kind == "buildings"
						child.Parent = main
					end
					main.Parent = staging
				end
			end
			staging:SetAttribute("Done", true)
			staging.Parent = root
			city:SetAttribute("Progress", ("%s %d/%d"):format(kind, n, #list))
			task.wait()
		end
	end
end

-- Lighting, terrain colors and terrain water (bay up to today's high tide).
-- NOTE: Lighting.Technology = Future must be set by hand (Studio blocks scripts from it).
function StyledBuilder.environment(manifest)
	local L = game:GetService("Lighting")
	L.ClockTime = 16.3
	L.GeographicLatitude = 37.8
	L.Brightness = 2.4
	L.OutdoorAmbient = Color3.fromRGB(132, 132, 140)
	L.Ambient = Color3.fromRGB(70, 70, 78)
	L.EnvironmentDiffuseScale = 1
	L.EnvironmentSpecularScale = 1
	L.ShadowSoftness = 0.25
	local function get(class, name)
		local i = L:FindFirstChild(name) or Instance.new(class)
		i.Name = name
		i.Parent = L
		return i
	end
	local a = get("Atmosphere", "Atmosphere")
	a.Density, a.Offset, a.Haze, a.Glare = 0.1, 0.12, 1.4, 0.2
	a.Color, a.Decay = Color3.fromRGB(206, 196, 178), Color3.fromRGB(112, 120, 138)
	local cc = get("ColorCorrectionEffect", "ColorCorrection")
	cc.Contrast, cc.Saturation, cc.TintColor = 0.08, 0.12, Color3.fromRGB(255, 248, 238)
	local bl = get("BloomEffect", "Bloom")
	bl.Intensity, bl.Size, bl.Threshold = 0.35, 24, 1.8
	local sr = get("SunRaysEffect", "SunRays")
	sr.Intensity, sr.Spread = 0.04, 0.6
	get("Sky", "Sky")

	local T = workspace.Terrain
	T:SetMaterialColor(Enum.Material.Pavement, Color3.fromRGB(150, 146, 138))
	T:SetMaterialColor(Enum.Material.Asphalt, Color3.fromRGB(62, 62, 66))
	T:SetMaterialColor(Enum.Material.Grass, Color3.fromRGB(98, 128, 62))
	T:SetMaterialColor(Enum.Material.Mud, Color3.fromRGB(88, 80, 66))
	T.WaterColor = Color3.fromRGB(28, 84, 98)
	T.WaterReflectance, T.WaterTransparency = 0.55, 0.35
	T.WaterWaveSize, T.WaterWaveSpeed = 0.12, 8
	local clouds = T:FindFirstChildOfClass("Clouds") or Instance.new("Clouds")
	clouds.Cover, clouds.Density = 0.42, 0.6
	clouds.Parent = T

	-- terrain water in the open bay, from 1 m below NAVD88 0 up to MHHW (the "today" water)
	local w = DataLoader.json(manifest.water)
	local y0, y1 = Config.m(-1.0), Config.m(Config.MHHW_M)
	for n, rc in ipairs(w.sea) do
		local x = rc[1]
		while x < rc[3] do
			local xw = math.min(1024, rc[3] - x)
			local z = rc[2]
			while z < rc[4] do
				local zw = math.min(1024, rc[4] - z)
				T:FillBlock(CFrame.new(x + xw / 2, (y0 + y1) / 2, z + zw / 2), Vector3.new(xw, y1 - y0, zw), Enum.Material.Water)
				z += zw
			end
			x += xw
		end
		if n % 40 == 0 then task.wait() end
	end
end

return StyledBuilder
