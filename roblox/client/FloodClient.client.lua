-- StarterPlayer.StarterPlayerScripts.FloodClient (LocalScript)
-- Runtime viewer: UI, scenario + map-mode controller, water, fly camera, viewpoints, walk mode
-- (street snapping, water depth at your feet, street names, FloodWatch block info), the
-- FloodWatch layer that matches Kai's website, a deep link from the website, click info.
-- Uses ONLY precomputed attributes + baked JSON modules (no HTTP, no flood recomputation).
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")
local HttpService = game:GetService("HttpService")

local FV = ReplicatedStorage:WaitForChild("FloodViewer")
local Config = require(FV:WaitForChild("Config"))
local Stats = HttpService:JSONDecode(require(FV:WaitForChild("StatsJSON")))
local fwMod = FV:FindFirstChild("FloodwatchJSON")
local FW = fwMod and HttpService:JSONDecode(require(fwMod)) or { hexes = {}, reports_total = 0, risk_counts = {} }
local city = workspace:WaitForChild("City")
local player = Players.LocalPlayer
local camera = workspace.CurrentCamera
local C = Config.COLORS
local m = Config.m
local SPM = Config.STUDS_PER_METER

-- ------------------------------------------------------------------ cache data
local buildings = {}
for _, p in ipairs(city:WaitForChild("Buildings"):GetDescendants()) do
	if p:IsA("BasePart") then
		local depth, pri = {}, {}
		for v in string.gmatch(p:GetAttribute("Depth") or "", "[^,]+") do table.insert(depth, tonumber(v)) end
		for v in string.gmatch(p:GetAttribute("Pri") or "", "[^,]+") do table.insert(pri, tonumber(v)) end
		table.insert(buildings, {
			part = p, depth = depth, pri = pri, risk = p:GetAttribute("Risk"),
			flooded = p:GetAttribute("Flooded") or "000000", cut = p:GetAttribute("Cut") or "000000",
			deg = p:GetAttribute("Deg") or "000000", contam = p:GetAttribute("Contam") or "000000",
			low = p:GetAttribute("Low") or "000000",
		})
	end
end
local roads = {}
for _, p in ipairs(city:WaitForChild("Roads"):GetDescendants()) do
	if p:IsA("BasePart") then table.insert(roads, { part = p, imp = p:GetAttribute("Imp") or "000000" }) end
end
local water = city:WaitForChild("Water")
local seaFolder = water:WaitForChild("Sea")
local seaParts = seaFolder:GetChildren()
local floodFolders = water:WaitForChild("Flood")
local markers = city:WaitForChild("Markers")
local sites = markers:WaitForChild("ContaminatedSites"):GetChildren()
local fwFolder = city:FindFirstChild("FloodWatch")
local fwOutlines = fwFolder and fwFolder:FindFirstChild("Outlines") and fwFolder.Outlines:GetChildren() or {}
local fwColumns = {}
if fwFolder and fwFolder:FindFirstChild("Columns") then
	for _, d in ipairs(fwFolder.Columns:GetDescendants()) do
		if d:IsA("BasePart") then table.insert(fwColumns, d) end
	end
end

local hexById, hexByH3 = {}, {}
for _, h in ipairs(FW.hexes) do hexById[h.id] = h; hexByH3[h.h3] = h end

local maxPri = {}
for i = 1, #Config.SCENARIOS do
	local mx = 0
	for _, b in ipairs(buildings) do mx = math.max(mx, b.pri[i] or 0) end
	maxPri[i] = mx
end

local state = { scenario = 1, mode = "Flood", busy = false, walking = false, panels = true }

local function flag(s, i) return string.sub(s or "", i, i) == "1" end

-- point (local meters) -> FloodWatch hex
local function hexAt(xm, zm)
	for _, h in ipairs(FW.hexes) do
		local dx, dz = xm - h.cx, zm - h.cz
		if dx * dx + dz * dz <= (h.r * 1.05) ^ 2 then
			local poly, inside, j = h.poly, false, #h.poly
			for i = 1, #poly do
				local xi, zi, xj, zj = poly[i][1], poly[i][2], poly[j][1], poly[j][2]
				if ((zi > zm) ~= (zj > zm)) and (xm < (xj - xi) * (zm - zi) / (zj - zi) + xi) then inside = not inside end
				j = i
			end
			if inside then return h end
		end
	end
end

-- ------------------------------------------------------------------ coloring
local function buildingColor(b, i, mode)
	local fl = flag(b.flooded, i)
	if mode == "Flood" then
		if fl then return C.floodShallow:Lerp(C.floodDeep, math.clamp((b.depth[i] or 0) / 2, 0, 1)) end
		if flag(b.low, i) then return C.lowLying end
		return C.building
	elseif mode == "Cut off" then
		if flag(b.cut, i) then return C.cutOff end
		if flag(b.deg, i) then return C.degraded end
		if fl then return C.floodShallow end
		return C.buildingDim
	elseif mode == "Contamination" then
		if flag(b.contam, i) then return C.contam end
		if fl then return C.floodShallow end
		return C.buildingDim
	elseif mode == "Priority" then
		local v = b.pri[i] or 0
		if v <= 0 or maxPri[i] <= 0 then return C.buildingDim end
		return C.priorityLow:Lerp(C.priorityHigh, math.clamp(v / maxPri[i], 0, 1))
	else -- FloodWatch: same colors as the website's hexes
		return b.risk and Config.RISK_COLORS[b.risk] or C.buildingDim
	end
end

local function setFloodWatchLayer()
	local on = state.mode == "FloodWatch"
	for n, p in ipairs(fwOutlines) do
		p.Transparency = on and 0.15 or 1
		if n % 3000 == 0 then task.wait() end
	end
	local cols = on and not state.walking
	for _, p in ipairs(fwColumns) do p.Transparency = cols and 0.45 or 1 end
end

local function recolor()
	local i, mode = state.scenario, state.mode
	for n, b in ipairs(buildings) do
		b.part.Color = buildingColor(b, i, mode)
		if n % 2000 == 0 then task.wait() end
	end
	local showImp = mode == "Flood" or mode == "Cut off"
	for n, r in ipairs(roads) do
		r.part.Color = (showImp and flag(r.imp, i)) and C.roadImpassable or C.road
		if n % 3000 == 0 then task.wait() end
	end
	for _, s in ipairs(sites) do
		local near = flag(s:GetAttribute("NearFlood"), i)
		s.Transparency = (mode == "Contamination") and (near and 0 or 0.7) or 1
		s.Color = near and C.contam or Color3.fromRGB(150, 150, 150)
	end
	setFloodWatchLayer()
end

local function setWater(i)
	local target = Stats.scenarios[i].water_level_studs
	local info = TweenInfo.new(1.5, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut)
	for _, p in ipairs(seaParts) do
		TweenService:Create(p, info, { Position = Vector3.new(p.Position.X, target - 1, p.Position.Z) }):Play()
	end
	for k, sid in ipairs(Config.SCENARIOS) do
		local f = floodFolders:FindFirstChild(sid)
		if f then
			for _, p in ipairs(f:GetChildren()) do p.Transparency = (k == i) and 0.3 or 1 end
		end
	end
end

-- ------------------------------------------------------------------ UI helpers
local gui = Instance.new("ScreenGui")
gui.Name = "FloodUI"
gui.ResetOnSpawn = false
gui.IgnoreGuiInset = true
gui.Parent = player:WaitForChild("PlayerGui")

local FONT = Enum.Font.GothamMedium
local MUTED = Color3.fromRGB(180, 190, 205)
local function frame(props)
	local f = Instance.new("Frame")
	f.BackgroundColor3 = Color3.fromRGB(18, 24, 34)
	f.BackgroundTransparency = 0.15
	f.BorderSizePixel = 0
	for k, v in pairs(props) do f[k] = v end
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, 10)
	c.Parent = f
	return f
end
local function text(parent, str, size, props)
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Font = FONT
	t.TextSize = size
	t.TextColor3 = Color3.new(1, 1, 1)
	t.TextXAlignment = Enum.TextXAlignment.Left
	t.TextWrapped = true
	t.Text = str
	t.Size = UDim2.new(1, 0, 0, size + 6)
	for k, v in pairs(props or {}) do t[k] = v end
	t.Parent = parent
	return t
end
local function list(parent, pad)
	local l = Instance.new("UIListLayout")
	l.Padding = UDim.new(0, pad or 6)
	l.SortOrder = Enum.SortOrder.LayoutOrder
	l.Parent = parent
	local p = Instance.new("UIPadding")
	for _, s in ipairs({ "PaddingTop", "PaddingBottom", "PaddingLeft", "PaddingRight" }) do p[s] = UDim.new(0, 12) end
	p.Parent = parent
end
local function clear(f)
	for _, c in ipairs(f:GetChildren()) do if c:IsA("GuiObject") then c:Destroy() end end
end
local function button(parent, label, w, onClick)
	local b = Instance.new("TextButton")
	b.Size = UDim2.fromOffset(w, 40)
	b.BackgroundColor3 = Color3.fromRGB(45, 60, 80)
	b.TextColor3 = Color3.new(1, 1, 1)
	b.Font = Enum.Font.GothamBold
	b.TextSize = 17
	b.Text = label
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, 8)
	c.Parent = b
	b.Parent = parent
	b.MouseButton1Click:Connect(onClick)
	return b
end
local function row(parent, pos, size)
	local r = Instance.new("Frame")
	r.BackgroundTransparency = 1
	r.Position, r.Size = pos, size
	local l = Instance.new("UIListLayout")
	l.FillDirection = Enum.FillDirection.Horizontal
	l.Padding = UDim.new(0, 6)
	l.Parent = r
	r.Parent = parent
	return r
end
local function fmt(n)
	local s = tostring(math.floor(n + 0.5))
	local withCommas = s:reverse():gsub("(%d%d%d)", "%1,"):reverse():gsub("^,", "")
	return withCommas
end
local function swatchRow(parent, color, label, order)
	local r = Instance.new("Frame")
	r.BackgroundTransparency = 1
	r.Size = UDim2.new(1, 0, 0, 22)
	r.LayoutOrder = order
	local sw = Instance.new("Frame")
	sw.Size = UDim2.fromOffset(18, 18)
	sw.BackgroundColor3 = color
	sw.BorderSizePixel = 0
	sw.Parent = r
	text(r, label, 16, { Position = UDim2.fromOffset(26, -2), Size = UDim2.new(1, -26, 0, 22) })
	r.Parent = parent
end

-- ------------------------------------------------------------------ layout
local top = frame({ Size = UDim2.new(1, -24, 0, 112), Position = UDim2.fromOffset(12, 12) })
top.Parent = gui
text(top, "Oakland Flood Consequence Explorer  ·  West Oakland & waterfront", 22,
	{ Position = UDim2.fromOffset(14, 8), Size = UDim2.new(1, -28, 0, 28), Font = Enum.Font.GothamBold })
local scenRow = row(top, UDim2.fromOffset(14, 44), UDim2.new(0.5, 0, 0, 44))
local modeRow = row(top, UDim2.new(0.5, 10, 0, 44), UDim2.new(0.5, -24, 0, 44))
local scenCaption = text(top, "Sea-level rise above today's high tide", 14,
	{ Position = UDim2.fromOffset(14, 88), Size = UDim2.new(0.5, 0, 0, 18), TextColor3 = MUTED })

local left = Instance.new("Frame")
left.BackgroundTransparency = 1
left.Size = UDim2.fromScale(1, 1)
left.Parent = gui
local statsPanel = frame({ Size = UDim2.fromOffset(380, 330), Position = UDim2.fromOffset(12, 136) })
statsPanel.Parent = left
list(statsPanel, 4)
local legend = frame({ Size = UDim2.fromOffset(380, 175), Position = UDim2.fromOffset(12, 476) })
legend.Parent = left
list(legend, 4)
local prio = frame({ Size = UDim2.fromOffset(400, 300), Position = UDim2.new(1, -412, 0, 136) })
prio.Parent = left
list(prio, 4)
local info = frame({ Size = UDim2.fromOffset(400, 230), Position = UDim2.new(1, -412, 0, 446), Visible = false })
info.Parent = gui
list(info, 2)

local bottom = frame({ Size = UDim2.new(1, -24, 0, 88), Position = UDim2.new(0, 12, 1, -100) })
bottom.Parent = gui
local vpRow = row(bottom, UDim2.fromOffset(14, 8), UDim2.new(1, -28, 0, 44))
text(bottom, "Exploration tool, not an official hazard or evacuation map. Flood extents: ART (BCDC); +5 ft uses ART's 5.5 ft map. Flooding today: FloodWatch (311 reports). Residents are estimates. Cleanup-site proximity is not exposure.  [H] hide panels",
	13, { Position = UDim2.fromOffset(14, 54), Size = UDim2.new(1, -28, 0, 30), TextColor3 = MUTED })

-- walk HUD (top center, only while walking)
local hud = frame({ Size = UDim2.fromOffset(520, 124), Position = UDim2.new(0.5, -260, 0, 136), Visible = false })
hud.Parent = gui
list(hud, 2)
local hudStreet = text(hud, "", 20, { Font = Enum.Font.GothamBold })
local hudWater = text(hud, "", 18)
local hudHex = text(hud, "", 15, { TextColor3 = MUTED, Size = UDim2.new(1, 0, 0, 60) })

local scenButtons, modeButtons = {}, {}

local LEGENDS = {
	["Flood"] = { { C.floodShallow, "Flooded (shallow)" }, { C.floodDeep, "Flooded (deep, 2 m+)" }, { C.lowLying, "Below water level but protected (low-lying)" }, { C.roadImpassable, "Road impassable (> 15 cm)" }, { C.building, "Dry" } },
	["Cut off"] = { { C.cutOff, "Cut off from fire or medical services" }, { C.degraded, "Response time more than doubles" }, { C.floodShallow, "Flooded" }, { C.roadImpassable, "Road impassable" } },
	["Contamination"] = { { C.contam, "Within 100 m of a cleanup site near flooding" }, { C.floodShallow, "Flooded" }, { Color3.fromRGB(150, 150, 150), "Cleanup site (not near flooding)" } },
	["Priority"] = { { C.priorityHigh, "Highest priority tract" }, { C.priorityLow, "Lower priority" }, { C.buildingDim, "Not exposed / not ranked" } },
	["FloodWatch"] = {},
}
for _, r in ipairs(Config.RISK_ORDER) do table.insert(LEGENDS.FloodWatch, { Config.RISK_COLORS[r], r .. " risk (flooding today)" }) end

local function refreshPanels()
	local i = state.scenario
	local s = Stats.scenarios[i]
	clear(statsPanel)
	if state.mode == "FloodWatch" then
		text(statsPanel, "Flooding today · FloodWatch", 22, { Font = Enum.Font.GothamBold })
		text(statsPanel, ("311 flood reports here (2013–2026):  %s"):format(fmt(FW.reports_total or 0)), 19, { LayoutOrder = 1 })
		local rc = FW.risk_counts or {}
		text(statsPanel, ("Very high risk blocks:  %d   ·   High:  %d"):format(rc["Very high"] or 0, rc["High"] or 0), 19, { LayoutOrder = 2 })
		text(statsPanel, "Same hexagons, categories and colors as the FloodWatch website. Columns = number of flood reports.", 15,
			{ LayoutOrder = 3, TextColor3 = MUTED, Size = UDim2.new(1, 0, 0, 40) })
		text(statsPanel, ("And at %s of sea-level rise: %s residents flooded, %s cut off."):format(Config.SCENARIO_LABELS[i],
			fmt(s.residents_affected), fmt(s.residents_cut_off)), 16, { LayoutOrder = 4, Size = UDim2.new(1, 0, 0, 44) })
		text(statsPanel, "Reports partly reflect who calls 311 (see FloodWatch README).", 13,
			{ LayoutOrder = 5, TextColor3 = MUTED, Size = UDim2.new(1, 0, 0, 34) })
	else
		text(statsPanel, ("%s  ·  %s view"):format(Config.SCENARIO_LABELS[i], state.mode), 22, { Font = Enum.Font.GothamBold })
		local lines = {
			("Residents affected:  %s"):format(fmt(s.residents_affected)),
			("Buildings flooded:  %s"):format(fmt(s.buildings_flooded)),
			("Critical facilities lost:  %d"):format(s.facilities_lost),
			("Residents cut off:  %s"):format(fmt(s.residents_cut_off)),
			("Cleanup sites near flooding:  %d"):format(s.contaminated_sites_near_flooding),
			("Impassable road:  %.1f km"):format(s.road_km_impassable),
		}
		for n, l in ipairs(lines) do text(statsPanel, l, 20, { LayoutOrder = n }) end
		text(statsPanel, s.art_level_in and (("Hazard: ART %d-inch map%s. Water level %.2f m NAVD88."):format(
			s.art_level_in, s.art_level_in ~= 12 * s.slr_ft and " (ART has no 60-inch map)" or "", s.water_level_navd88_m))
			or "Hazard: LiDAR bathtub model (fallback).", 13, { LayoutOrder = 10, TextColor3 = MUTED, Size = UDim2.new(1, 0, 0, 40) })
	end

	clear(legend)
	text(legend, "Legend: " .. state.mode, 18, { Font = Enum.Font.GothamBold })
	for n, r in ipairs(LEGENDS[state.mode]) do swatchRow(legend, r[1], r[2], n) end

	clear(prio)
	if state.mode == "FloodWatch" then
		text(prio, "Highest-risk blocks today (FloodWatch)", 18, { Font = Enum.Font.GothamBold })
		local sorted = table.clone(FW.hexes)
		table.sort(sorted, function(a, b) return a.fvi_pct > b.fvi_pct end)
		for n = 1, math.min(5, #sorted) do
			local h = sorted[n]
			text(prio, ("%d. %s risk · higher than %d%% of Oakland\n    %d flood reports%s"):format(n, h.risk, h.fvi_pct,
				h.reports, h.under and " · may be under-reported" or ""), 15, { LayoutOrder = n, Size = UDim2.new(1, 0, 0, 42) })
		end
	else
		text(prio, "Where help should start (" .. Config.SCENARIO_LABELS[i] .. ")", 18, { Font = Enum.Font.GothamBold })
		local tops = Stats.top_priority[Config.SCENARIOS[i]] or {}
		if #tops == 0 then text(prio, "No exposed tracts at this level.", 16, { LayoutOrder = 1 }) end
		for n, t in ipairs(tops) do
			text(prio, ("%d. Tract %s (%s) · CES %d%%ile\n    %s flooded bldgs · %s residents · %s cut off"):format(
				t.rank, string.sub(t.tract_id, 6, 9) .. "." .. string.sub(t.tract_id, 10, 11), t.city, math.floor(t.ces_pctl),
				fmt(t.buildings_flooded), fmt(t.residents_affected), fmt(t.residents_cut_off)), 15,
				{ LayoutOrder = n, Size = UDim2.new(1, 0, 0, 42) })
		end
	end

	for k, b in ipairs(scenButtons) do b.BackgroundColor3 = (k == i) and Color3.fromRGB(40, 110, 190) or Color3.fromRGB(45, 60, 80) end
	for name, b in pairs(modeButtons) do b.BackgroundColor3 = (name == state.mode) and Color3.fromRGB(190, 90, 40) or Color3.fromRGB(45, 60, 80) end
end

local function apply()
	if state.busy then return end
	state.busy = true
	refreshPanels()
	setWater(state.scenario)
	recolor()
	state.busy = false
end

for i in ipairs(Config.SCENARIOS) do
	scenButtons[i] = button(scenRow, Config.SCENARIO_LABELS[i], 86, function() state.scenario = i; apply() end)
end
for _, name in ipairs(Config.MODES) do
	modeButtons[name] = button(modeRow, name, 122, function() state.mode = name; apply() end)
end

local function setPanels(on)
	state.panels = on
	left.Visible = on
	top.Visible = on
	bottom.Visible = on
	if not on then info.Visible = false end
end

-- ------------------------------------------------------------------ camera + walking
local W_STUDS, H_STUDS = m(7076), m(4492)
local camPos = Vector3.new(W_STUDS * 0.62, 2600, -H_STUDS * 0.05)
local yaw, pitch = math.rad(180), math.rad(-42)
local speedTiers = { 40, 120, 400, 1200 }
local speedIdx = 3
local vel = Vector3.zero

-- target = ground point (local meters) used when walking
local VIEWS = {
	{ "Overview", Vector3.new(W_STUDS * 0.62, 2600, -H_STUDS * 0.05), 180, -42, { 4600, -420 } },
	{ "West Oakland", Vector3.new(m(3300), 700, m(-1700)), 200, -35, { 3350, -2150 } },
	-- walk target = Jefferson St (Jack London district): dry today and at +3 ft, ~0.3 m at +4 ft,
	-- ~0.7 m at +5 ft, so the wading readout shows up on a single click (docs/demo_script.md)
	{ "Jack London", Vector3.new(m(4700), 420, m(-150)), 170, -30, { 4816, -749 } },
	{ "Port", Vector3.new(m(1500), 900, m(-1800)), 235, -35, { 1900, -2000 } },
	{ "Fire Station 2", Vector3.new(m(4420), 300, m(-60)), 160, -30, { 4400, -230 } },
}

local function humanoid()
	local c = player.Character
	return c and c:FindFirstChildOfClass("Humanoid"), c and c:FindFirstChild("HumanoidRootPart")
end

-- walkable = not a freeway / ramp / bridge (you can't stand on those as a pedestrian)
local NOT_WALKABLE = { motorway = true, trunk = true }
for _, r in ipairs(roads) do
	r.walkable = not NOT_WALKABLE[r.part:GetAttribute("Hwy") or ""] and not r.part:GetAttribute("Elevated")
end

local function nearestStreet(pos, radius, walkableOnly)
	local best, bd = nil, radius or math.huge
	for _, r in ipairs(roads) do
		if not walkableOnly or r.walkable then
			local dm = ((r.part.Position - pos) * Vector3.new(1, 0, 1)).Magnitude
			if dm < bd then best, bd = r.part, dm end
		end
	end
	return best, bd
end

local function placeOnStreet(xs, zs)
	local hum, root = humanoid()
	if not (hum and root) then return false end
	local street = nearestStreet(Vector3.new(xs, 0, zs), 800, true)
	local target = street and street.Position or Vector3.new(xs, 0, zs)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Include
	params.FilterDescendantsInstances = { workspace.Terrain }
	local hit = workspace:Raycast(Vector3.new(target.X, 3000, target.Z), Vector3.new(0, -6000, 0), params)
	local y = hit and hit.Position.Y or 30
	player.Character:PivotTo(CFrame.new(target.X, y + 5, target.Z) * CFrame.Angles(0, yaw, 0))
	return true
end

local walkBtn
local function setWalking(on, xs, zs)
	local hum = humanoid()
	if on and not hum then return end
	state.walking = on
	if on then
		placeOnStreet(xs or camPos.X, zs or camPos.Z)
		camera.CameraType = Enum.CameraType.Custom
		hum.WalkSpeed = Config.WALK_SPEED
		walkBtn.Text = "Fly"
	else
		local _, root = humanoid()
		local p = root and root.Position or camPos
		camPos, pitch = p + Vector3.new(0, 250, m(150)), math.rad(-40)
		camera.CameraType = Enum.CameraType.Scriptable
		walkBtn.Text = "Walk here"
	end
	hud.Visible = on
	setFloodWatchLayer()
end

local function goTo(v)
	if state.walking then
		placeOnStreet(m(v[5][1]), m(v[5][2]))
		return
	end
	camera.CameraType = Enum.CameraType.Scriptable
	camPos, yaw, pitch = v[2], math.rad(v[3]), math.rad(v[4])
end
for _, v in ipairs(VIEWS) do button(vpRow, v[1], 150, function() goTo(v) end) end
walkBtn = button(vpRow, "Walk here", 150, function() setWalking(not state.walking) end)

UserInputService.InputChanged:Connect(function(input, gp)
	if state.walking or gp then return end
	if input.UserInputType == Enum.UserInputType.MouseMovement and UserInputService:IsMouseButtonPressed(Enum.UserInputType.MouseButton2) then
		yaw -= input.Delta.X * 0.004
		pitch = math.clamp(pitch - input.Delta.Y * 0.004, math.rad(-89), math.rad(30))
	elseif input.UserInputType == Enum.UserInputType.MouseWheel then
		speedIdx = math.clamp(speedIdx + (input.Position.Z > 0 and 1 or -1), 1, #speedTiers)
	end
end)

RunService.RenderStepped:Connect(function(dt)
	if state.walking then return end
	camera.CameraType = Enum.CameraType.Scriptable
	UserInputService.MouseBehavior = UserInputService:IsMouseButtonPressed(Enum.UserInputType.MouseButton2)
		and Enum.MouseBehavior.LockCurrentPosition or Enum.MouseBehavior.Default
	local rot = CFrame.Angles(0, yaw, 0) * CFrame.Angles(pitch, 0, 0)
	local move = Vector3.zero
	local function down(k) return UserInputService:IsKeyDown(k) end
	if down(Enum.KeyCode.W) then move += rot.LookVector end
	if down(Enum.KeyCode.S) then move -= rot.LookVector end
	if down(Enum.KeyCode.D) then move += rot.RightVector end
	if down(Enum.KeyCode.A) then move -= rot.RightVector end
	if down(Enum.KeyCode.E) then move += Vector3.yAxis end
	if down(Enum.KeyCode.Q) then move -= Vector3.yAxis end
	local speed = speedTiers[speedIdx] * (down(Enum.KeyCode.LeftShift) and 5 or 1)
	local target = move.Magnitude > 0 and move.Unit * speed or Vector3.zero
	vel = vel:Lerp(target, math.clamp(dt * 6, 0, 1))
	camPos += vel * dt
	camera.CFrame = CFrame.new(camPos) * rot
end)

-- walk HUD: street, water depth at your feet (wading slows you down), FloodWatch block
local DEPTH_WORDS = { { 0.15, "ankle-deep (roads close above 15 cm)" }, { 0.5, "knee-deep" }, { 1.0, "waist-deep" },
	{ 1.5, "chest-deep" }, { math.huge, "over your head" } }
local hudClock = 0
RunService.Heartbeat:Connect(function(dt)
	if not state.walking then return end
	hudClock += dt
	if hudClock < 0.2 then return end
	hudClock = 0
	local hum, root = humanoid()
	if not (hum and root) then return end
	local pos = root.Position
	-- ground under the player (terrain)
	local tp = RaycastParams.new()
	tp.FilterType = Enum.RaycastFilterType.Include
	tp.FilterDescendantsInstances = { workspace.Terrain }
	local g = workspace:Raycast(pos + Vector3.new(0, 4, 0), Vector3.new(0, -60, 0), tp)
	-- visible water above that ground (current scenario's flood layer + the bay)
	local depthM = 0
	if g then
		local wp = RaycastParams.new()
		wp.FilterType = Enum.RaycastFilterType.Include
		wp.FilterDescendantsInstances = { floodFolders:FindFirstChild(Config.SCENARIOS[state.scenario]), seaFolder }
		local w = workspace:Raycast(g.Position + Vector3.new(0, 0.2, 0), Vector3.new(0, 200, 0), wp)
		if w and w.Instance.Transparency < 1 then
			depthM = (w.Instance.Position.Y + w.Instance.Size.Y / 2 - g.Position.Y) / SPM
		end
	end
	local sprint = UserInputService:IsKeyDown(Enum.KeyCode.LeftShift)
	if depthM > 1.0 then hum.WalkSpeed = Config.DEEP_WADE_SPEED
	elseif depthM > 0.3 then hum.WalkSpeed = Config.WADE_SPEED
	else hum.WalkSpeed = sprint and Config.SPRINT_SPEED or Config.WALK_SPEED end
	if depthM > 0.02 then
		local word = DEPTH_WORDS[#DEPTH_WORDS][2]
		for _, d in ipairs(DEPTH_WORDS) do if depthM < d[1] then word = d[2] break end end
		hudWater.Text = ("Water here: %.2f m (%.1f ft), %s"):format(depthM, depthM / 0.3048, word)
		hudWater.TextColor3 = Color3.fromRGB(140, 200, 255)
	else
		hudWater.Text = "Dry here at " .. Config.SCENARIO_LABELS[state.scenario]
		hudWater.TextColor3 = Color3.new(1, 1, 1)
	end
	local street, d = nearestStreet(pos, 120, true)
	hudStreet.Text = (street and d < 120 and street:GetAttribute("Street")) or "Off-street"
	local h = hexAt(pos.X / SPM, pos.Z / SPM)
	local share = h and h.slr and h.slr[Config.SCENARIOS[state.scenario]]
	hudHex.Text = h and (("FloodWatch block: %s risk today · higher than %d%% of Oakland · %d flood reports to 311%s"):format(
		h.risk, h.fvi_pct, h.reports, (share and state.scenario > 1) and ("\nAt %s: %.0f%% of this block floods"):format(
		Config.SCENARIO_LABELS[state.scenario], share * 100) or "")) or "Outside FloodWatch coverage (Oakland only)"
end)

-- ------------------------------------------------------------------ click info
local function hexPanel(h)
	text(info, ("%s risk (flooding today)"):format(h.risk), 18, { Font = Enum.Font.GothamBold, TextColor3 = Config.RISK_COLORS[h.risk] })
	text(info, ("Higher than %d%% of Oakland areas"):format(h.fvi_pct), 15)
	text(info, ("%d flood reports to 311 (2013–2026)%s"):format(h.reports, h.under and " · may be under-reported" or ""), 15)
	text(info, ("Flood hazard rank: %d percentile · %s"):format(h.hazard_pct, h.fema), 14)
	if h.why ~= "" then text(info, "Why: " .. h.why, 14, { Size = UDim2.new(1, 0, 0, 36), TextColor3 = MUTED }) end
	local share = h.slr and h.slr[Config.SCENARIOS[state.scenario]]
	if share then
		text(info, ("And at %s of sea-level rise: %.0f%% of this block's land floods"):format(
			Config.SCENARIO_LABELS[state.scenario], share * 100), 14, { TextColor3 = Color3.fromRGB(140, 200, 255) })
	end
	text(info, ("Households without a car: %.0f%% · hex %s"):format(h.no_car, h.h3), 13, { TextColor3 = MUTED })
end

UserInputService.InputBegan:Connect(function(input, gp)
	if gp then return end
	if input.KeyCode == Enum.KeyCode.H then setPanels(not state.panels) return end
	if input.UserInputType ~= Enum.UserInputType.MouseButton1 then return end
	local ray = camera:ViewportPointToRay(input.Position.X, input.Position.Y)
	local params = RaycastParams.new()
	local targets = { city.Buildings, markers }
	if fwFolder and state.mode == "FloodWatch" and not state.walking then table.insert(targets, fwFolder.Columns) end
	params.FilterDescendantsInstances = targets
	params.FilterType = Enum.RaycastFilterType.Include
	local hit = workspace:Raycast(ray.Origin, ray.Direction * 20000, params)
	clear(info)
	if not hit then info.Visible = false return end
	local p, i = hit.Instance, state.scenario
	info.Visible = true
	if p:GetAttribute("HexId") then
		hexPanel(hexById[p:GetAttribute("HexId")])
		return
	elseif p:GetAttribute("Kind") == "facility" then
		text(info, p.Name, 18, { Font = Enum.Font.GothamBold })
		text(info, ("Type: %s"):format((string.gsub(p:GetAttribute("Type"), "_", " "))), 16)
		text(info, flag(p:GetAttribute("Flooded"), i) and "FLOODED at this level" or "Not flooded at this level", 16)
		return
	elseif p:GetAttribute("Kind") == "site" then
		text(info, p.Name, 18, { Font = Enum.Font.GothamBold })
		text(info, ("%s · %s"):format(p:GetAttribute("Source"), p:GetAttribute("Category")), 15)
		text(info, flag(p:GetAttribute("NearFlood"), i) and "Within 100 m of flooding (proximity, not exposure)" or "Not near flooding at this level", 15)
		return
	end
	if state.mode == "FloodWatch" and p:GetAttribute("Hex") and hexById[p:GetAttribute("Hex")] then
		hexPanel(hexById[p:GetAttribute("Hex")])
		return
	end
	local depth = {}
	for v in string.gmatch(p:GetAttribute("Depth") or "", "[^,]+") do table.insert(depth, tonumber(v)) end
	text(info, "Building " .. p.Name, 18, { Font = Enum.Font.GothamBold })
	local d = depth[i] or 0
	text(info, flag(p:GetAttribute("Flooded"), i) and ("Flooded: about %.1f m (%.1f ft) deep (estimate)"):format(d, d / 0.3048)
		or (flag(p:GetAttribute("Low"), i) and "Dry, but below the water level (low-lying)" or "Dry at this level"), 16)
	text(info, flag(p:GetAttribute("Cut"), i) and "Cut off from emergency services" or
		(flag(p:GetAttribute("Deg"), i) and "Emergency response time more than doubles" or "Emergency access OK"), 16)
	text(info, ("Height %.0f m%s · ~%.0f residents (estimate)"):format(p:GetAttribute("HeightM"),
		p:GetAttribute("HeightEstimated") and " (estimated)" or "", p:GetAttribute("Residents")), 15)
	local ces = p:GetAttribute("CES")
	text(info, ("Tract %s · CalEnviroScreen %s"):format(p:GetAttribute("Tract"), ces and ces >= 0 and ("%d%%ile"):format(ces) or "n/a"), 15)
	local h = p:GetAttribute("Hex") and hexById[p:GetAttribute("Hex")]
	if h then text(info, ("Flooding today (FloodWatch): %s risk, %d reports"):format(h.risk, h.reports), 14, { TextColor3 = MUTED }) end
end)

-- ------------------------------------------------------------------ deep link from FloodWatch
local function handleLaunch()
	local h3 = player:GetAttribute("LaunchHex")
	local h = h3 and hexByH3[h3]
	if not h then return end
	state.mode = "FloodWatch"
	apply()
	if not player.Character then player.CharacterAdded:Wait() end
	task.wait(1)
	setWalking(true, m(h.cx), m(h.cz))
end
player:GetAttributeChangedSignal("LaunchHex"):Connect(handleLaunch)

goTo(VIEWS[1])
apply()
task.spawn(handleLaunch)
