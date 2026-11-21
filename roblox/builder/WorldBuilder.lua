-- ServerStorage.FloodBuilder.WorldBuilder (ModuleScript). Edit-mode build only.
-- Creates buildings, roads, water surfaces and markers from data/processed/roblox/.
-- All flood data is stored as ATTRIBUTES so runtime scripts only recolor / show / hide.
-- Each shard folder gets Done=true when complete, so a rerun skips finished work.
local Config = require(game:GetService("ReplicatedStorage").FloodViewer.Config)
local DataLoader = require(script.Parent.DataLoader)

local WorldBuilder = {}
local m = Config.m
local MAX_PART = 2048

local function folder(parent, name)
	local f = parent:FindFirstChild(name)
	if not f then
		f = Instance.new("Folder")
		f.Name = name
		f.Parent = parent
	end
	return f
end
WorldBuilder.folder = folder

local function basePart(name)
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.CanCollide = false
	p.CanTouch = false
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Material = Enum.Material.SmoothPlastic
	return p
end

-- ------------------------------------------------------------------ buildings
function WorldBuilder.buildings(manifest, city, shardFilter)
	local root = folder(city, "Buildings")
	local total = 0
	for n, path in ipairs(manifest.buildings) do
		local cellName = path:match("cell_[%d_]+")
		if (not shardFilter or shardFilter[cellName]) then
			local f = root:FindFirstChild(cellName)
			if not (f and f:GetAttribute("Done")) then
				if f then f:Destroy() end
				local recs = DataLoader.json(path)
				local staging = Instance.new("Folder")
				staging.Name = cellName
				for _, r in ipairs(recs) do
					local p = basePart(tostring(r.id))
					p.CanQuery = true
					p.CanCollide = true -- walk mode: walk around buildings, not through them
					local h = m(r.h + Config.BUILDING_SINK_M)
					p.Size = Vector3.new(m(r.w), h, m(r.d))
					local y = m(r.base - Config.BUILDING_SINK_M) + h / 2
					p.CFrame = CFrame.new(m(r.cx), y, m(r.cz)) * CFrame.Angles(0, math.rad(r.rot), 0)
					p.Color = Config.COLORS.building
					p:SetAttribute("Flooded", r.flooded)
					p:SetAttribute("Cut", r.cut)
					p:SetAttribute("Deg", r.deg)
					p:SetAttribute("Contam", r.contam)
					p:SetAttribute("Low", r.low)
					p:SetAttribute("Depth", table.concat(r.depth, ","))
					p:SetAttribute("Pri", table.concat(r.pri, ","))
					p:SetAttribute("Tract", r.tract or "")
					p:SetAttribute("CES", r.ces or -1)
					p:SetAttribute("Residents", r.res)
					p:SetAttribute("HeightM", r.h)
					p:SetAttribute("HeightEstimated", r.est)
					p.Parent = staging
				end
				staging:SetAttribute("Done", true)
				staging.Parent = root -- one parent write per shard (bounded cost)
				total += #recs
				city:SetAttribute("Progress", ("buildings shard %d/%d"):format(n, #manifest.buildings))
				task.wait()
			end
		end
	end
	return total
end

-- ------------------------------------------------------------------ roads
function WorldBuilder.roads(manifest, city, shardFilter)
	local root = folder(city, "Roads")
	for n, path in ipairs(manifest.roads) do
		local cellName = path:match("cell_[%d_]+")
		if not shardFilter or shardFilter[cellName] then
			local f = root:FindFirstChild(cellName)
			if not (f and f:GetAttribute("Done")) then
				if f then f:Destroy() end
				local staging = Instance.new("Folder")
				staging.Name = cellName
				for ri, r in ipairs(DataLoader.json(path)) do
					local w = m(r.width_m)
					for i = 1, #r.pts - 1 do
						local a, b = r.pts[i], r.pts[i + 1]
						local pa = Vector3.new(m(a[1]), m(a[3]) + 0.3, m(a[2]))
						local pb = Vector3.new(m(b[1]), m(b[3]) + 0.3, m(b[2]))
						local len = (pb - pa).Magnitude
						if len > 0.5 then
							local p = basePart(("r%d_%d"):format(ri, i))
							p.CanQuery = false
							p.CastShadow = false
							p.Size = Vector3.new(w, 0.4, len + w * 0.5)
							p.CFrame = CFrame.lookAt((pa + pb) / 2, pb)
							p.Color = Config.COLORS.road
							p:SetAttribute("Imp", r.imp)
							if r.name then p:SetAttribute("Street", r.name) end
							p:SetAttribute("Hwy", r.hwy or "")
							p:SetAttribute("Elevated", r.elevated == true)
							p.Parent = staging
						end
					end
				end
				staging:SetAttribute("Done", true)
				staging.Parent = root
				city:SetAttribute("Progress", ("roads shard %d/%d"):format(n, #manifest.roads))
				task.wait()
			end
		end
	end
end

-- ------------------------------------------------------------------ water
-- Rectangles are in studs [x0, z0, x1, z1]; split anything larger than 2048 studs.
local function waterParts(rects, parent, levelStuds, color, transparency, prefix)
	local count = 0
	for _, rc in ipairs(rects) do
		local x0, z0, x1, z1 = rc[1], rc[2], rc[3], rc[4]
		local x = x0
		while x < x1 do
			local xw = math.min(MAX_PART, x1 - x)
			local z = z0
			while z < z1 do
				local zw = math.min(MAX_PART, z1 - z)
				local p = basePart(prefix)
				p.CanQuery = true -- walk mode raycasts up from the ground to measure water depth
				p.CastShadow = false
				p.Size = Vector3.new(xw, 2, zw)
				p.Position = Vector3.new(x + xw / 2, levelStuds - 1, z + zw / 2)
				p.Color = color
				p.Transparency = transparency
				p.Material = Enum.Material.SmoothPlastic -- Glass mirrors the sky and hides the city
				p.Parent = parent
				count += 1
				z += zw
			end
			x += xw
		end
	end
	return count
end

function WorldBuilder.water(manifest, city, scenarioLevels)
	local root = folder(city, "Water")
	if root:GetAttribute("Done") then return end
	root:ClearAllChildren()
	local w = DataLoader.json(manifest.water)
	local sea = folder(root, "Sea")
	waterParts(w.sea, sea, m(Config.MHHW_M), Config.COLORS.water, 0.25, "sea")
	local inland = folder(root, "Inland")
	waterParts(w.inland, inland, m(w.inland_level_m), Config.COLORS.inlandWater, 0.25, "lake")
	local flood = folder(root, "Flood")
	for i, sid in ipairs(Config.SCENARIOS) do
		local f = folder(flood, sid)
		local n = waterParts(w.flood[sid] or {}, f, m(scenarioLevels[i]), Config.COLORS.water, 1, "flood")
		f:SetAttribute("Parts", n)
		f:SetAttribute("LevelStuds", m(scenarioLevels[i]))
		task.wait()
	end
	root:SetAttribute("Done", true)
end

-- ------------------------------------------------------------------ markers
local function label(parent, text, color)
	local bb = Instance.new("BillboardGui")
	bb.Size = UDim2.fromOffset(220, 40)
	bb.StudsOffset = Vector3.new(0, 6, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 2500
	local t = Instance.new("TextLabel")
	t.Size = UDim2.fromScale(1, 1)
	t.BackgroundTransparency = 1
	t.Text = text
	t.TextColor3 = color
	t.TextStrokeTransparency = 0.3
	t.Font = Enum.Font.GothamBold
	t.TextScaled = true
	t.Parent = bb
	bb.Parent = parent
end

function WorldBuilder.markers(manifest, city)
	local root = folder(city, "Markers")
	if root:GetAttribute("Done") then return end
	root:ClearAllChildren()
	local fac = folder(root, "Facilities")
	for _, f in ipairs(DataLoader.json(manifest.facilities)) do
		local p = basePart(f.name)
		p.Shape = Enum.PartType.Cylinder
		p.Size = Vector3.new(60, 10, 10) -- cylinder axis = X; rotate upright
		p.CFrame = CFrame.new(m(f.x), m(f.elev) + 30, m(f.z)) * CFrame.Angles(0, 0, math.rad(90))
		p.Color = Config.FACILITY_COLORS[f.type] or Color3.new(1, 1, 1)
		p.Material = Enum.Material.Neon
		p.CanQuery = true
		p:SetAttribute("Kind", "facility")
		p:SetAttribute("Type", f.type)
		p:SetAttribute("Flooded", f.flooded)
		label(p, f.name, p.Color)
		p.Parent = fac
	end
	local sites = folder(root, "ContaminatedSites")
	for _, s in ipairs(DataLoader.json(manifest.contaminated_sites)) do
		local p = basePart(s.name)
		p.Shape = Enum.PartType.Ball
		p.Size = Vector3.new(14, 14, 14)
		p.Position = Vector3.new(m(s.x), m(s.elev) + 8, m(s.z))
		p.Color = Config.COLORS.contam
		p.Material = Enum.Material.Neon
		p.Transparency = 1 -- shown only in Contamination mode
		p.CanQuery = true
		p:SetAttribute("Kind", "site")
		p:SetAttribute("Category", s.category)
		p:SetAttribute("Source", s.source)
		p:SetAttribute("InFlood", s.in_flood)
		p:SetAttribute("NearFlood", s.near_flood)
		p.Parent = sites
	end
	root:SetAttribute("Done", true)
end

-- ------------------------------------------------------------------ FloodWatch (Kai's website)
-- Same hexes as the FloodWatch website: ground outlines from the website's own geometry,
-- translucent 3D columns (height = 311 flood reports), building Hex/Risk attributes, and a
-- FloodwatchJSON module for the client panels.
local SQRT3 = math.sqrt(3)

local function groundY(xs, zs)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = { workspace.Terrain }
	local hit = workspace:Raycast(Vector3.new(xs, 2000, zs), Vector3.new(0, -4000, 0), params)
	return hit and hit.Position.Y or 0
end

function WorldBuilder.floodwatch(city)
	local HttpService = game:GetService("HttpService")
	local fw = DataLoader.json("floodwatch.json")
	-- client data (no per-building list, no outline points)
	local client = { source = fw.source, reports_total = fw.reports_total, risk_counts = fw.risk_counts,
		note = fw.note, hexes = fw.hexes }
	-- always a fresh instance: require() caches a ModuleScript's first result per session
	local fv = game:GetService("ReplicatedStorage").FloodViewer
	if fv:FindFirstChild("FloodwatchJSON") then fv.FloodwatchJSON:Destroy() end
	local mod = Instance.new("ModuleScript")
	mod.Name = "FloodwatchJSON"
	mod.Source = "-- generated from data/processed/roblox/floodwatch.json (FloodWatch, Kai); do not edit\nreturn [==["
		.. HttpService:JSONEncode(client) .. "]==]\n"
	mod.Parent = game:GetService("ReplicatedStorage").FloodViewer

	local root = folder(city, "FloodWatch")
	root:ClearAllChildren()
	local byId = {}
	for _, h in ipairs(fw.hexes) do byId[h.id] = h end

	-- building attributes
	local partsById = {}
	for _, p in ipairs(city.Buildings:GetDescendants()) do
		-- only the main (wall) parts: roofs/details are children without the flood attributes
		local id = tonumber(p.Name)
		if id and p:IsA("BasePart") and p:GetAttribute("Flooded") then partsById[id] = p end
	end
	for n, bh in ipairs(fw.bldg_hex) do
		local p, h = partsById[bh[1]], byId[bh[2]]
		if p and h then
			p:SetAttribute("Hex", h.id)
			p:SetAttribute("Risk", h.risk)
		end
		if n % 3000 == 0 then task.wait() end
	end

	-- outlines on the ground (white, like the website's hex borders)
	local outl = Instance.new("Folder")
	outl.Name = "Outlines"
	for _, e in ipairs(fw.edges) do
		for i = 1, #e - 1 do
			local a, b = e[i], e[i + 1]
			local pa = Vector3.new(m(a[1]), m(a[3]) + 0.8, m(a[2]))
			local pb = Vector3.new(m(b[1]), m(b[3]) + 0.8, m(b[2]))
			local len = (pb - pa).Magnitude
			if len > 0.5 then
				local p = basePart("edge")
				p.CanQuery = false
				p.CastShadow = false
				p.Size = Vector3.new(1.4, 1.6, len + 1.4)
				p.CFrame = CFrame.lookAt((pa + pb) / 2, pb)
				p.Color = Color3.new(1, 1, 1)
				p.Material = Enum.Material.Neon
				p.Transparency = 1 -- shown in FloodWatch mode
				p.Parent = outl
			end
		end
	end
	outl.Parent = root
	task.wait()

	-- 3D columns: a regular hexagon = 3 boxes (sqrt3*R x R) rotated 60 degrees apart
	local cols = Instance.new("Folder")
	cols.Name = "Columns"
	for _, h in ipairs(fw.hexes) do
		local cx, cz, R = m(h.cx), m(h.cz), m(h.r)
		local y0 = groundY(cx, cz)
		local hgt = m(math.clamp(6 + 2.5 * h.reports, 6, 140))
		local col = Instance.new("Model")
		col.Name = h.h3
		for k = 0, 2 do
			local p = basePart("hex")
			p.CanQuery = true
			p.CastShadow = false
			p.Size = Vector3.new(SQRT3 * R, hgt, R)
			p.CFrame = CFrame.new(cx, y0 + hgt / 2, cz) * CFrame.Angles(0, math.rad(h.rot + 30 + 60 * k), 0)
			p.Color = Config.RISK_COLORS[h.risk] or Color3.new(1, 1, 1)
			p.Transparency = 1 -- shown in FloodWatch mode while flying
			p:SetAttribute("HexId", h.id)
			p.Parent = col
		end
		col:SetAttribute("HexId", h.id)
		col.Parent = cols
	end
	cols.Parent = root
	root:SetAttribute("Source", fw.source)
	root:SetAttribute("Done", true)
	return #fw.hexes
end

return WorldBuilder
