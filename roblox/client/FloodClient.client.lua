-- StarterPlayer.StarterPlayerScripts.FloodClient (LocalScript)
-- Runtime viewer: UI, scenario + map-mode controller, water, fly camera, viewpoints, walk
-- mode, click-a-building info. Uses ONLY precomputed attributes + StatsJSON (no HTTP, no
-- flood recomputation in Luau).
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")
local HttpService = game:GetService("HttpService")

local FV = ReplicatedStorage:WaitForChild("FloodViewer")
local Config = require(FV:WaitForChild("Config"))
local Stats = HttpService:JSONDecode(require(FV:WaitForChild("StatsJSON")))
local city = workspace:WaitForChild("City")
local player = Players.LocalPlayer
local camera = workspace.CurrentCamera
local C = Config.COLORS
local m = Config.m

-- ------------------------------------------------------------------ cache building data
local buildings = {}
for _, p in ipairs(city:WaitForChild("Buildings"):GetDescendants()) do
	if p:IsA("BasePart") then
		local depth, pri = {}, {}
		for v in string.gmatch(p:GetAttribute("Depth") or "", "[^,]+") do table.insert(depth, tonumber(v)) end
		for v in string.gmatch(p:GetAttribute("Pri") or "", "[^,]+") do table.insert(pri, tonumber(v)) end
		table.insert(buildings, {
			part = p, depth = depth, pri = pri,
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
local seaParts = water:WaitForChild("Sea"):GetChildren()
local floodFolders = water:WaitForChild("Flood")
local markers = city:WaitForChild("Markers")
local sites = markers:WaitForChild("ContaminatedSites"):GetChildren()

local maxPri = {}
for i = 1, #Config.SCENARIOS do
	local mx = 0
	for _, b in ipairs(buildings) do mx = math.max(mx, b.pri[i] or 0) end
	maxPri[i] = mx
end

local state = { scenario = 1, mode = "Flood", busy = false }

local function flag(s, i) return string.sub(s, i, i) == "1" end

-- ------------------------------------------------------------------ coloring
local function buildingColor(b, i, mode)
	local fl = flag(b.flooded, i)
	if mode == "Flood" then
		if fl then
			return C.floodShallow:Lerp(C.floodDeep, math.clamp((b.depth[i] or 0) / 2, 0, 1))
		elseif flag(b.low, i) then
			return C.lowLying
		end
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
	else -- Priority (tract priority score for this scenario)
		local v = b.pri[i] or 0
		if v <= 0 or maxPri[i] <= 0 then return C.buildingDim end
		return C.priorityLow:Lerp(C.priorityHigh, math.clamp(v / maxPri[i], 0, 1))
	end
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
		local near = flag(s:GetAttribute("NearFlood") or "000000", i)
		s.Transparency = (mode == "Contamination") and (near and 0 or 0.7) or 1
		s.Color = near and C.contam or Color3.fromRGB(150, 150, 150)
	end
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
			for _, p in ipairs(f:GetChildren()) do
				p.Transparency = (k == i) and 0.3 or 1
			end
		end
	end
end

-- ------------------------------------------------------------------ UI
local gui = Instance.new("ScreenGui")
gui.Name = "FloodUI"
gui.ResetOnSpawn = false
gui.IgnoreGuiInset = true
gui.Parent = player:WaitForChild("PlayerGui")

local FONT = Enum.Font.GothamMedium
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
	return l
end
local function button(parent, label, w, onClick)
	local b = Instance.new("TextButton")
	b.Size = UDim2.fromOffset(w, 40)
	b.BackgroundColor3 = Color3.fromRGB(45, 60, 80)
	b.TextColor3 = Color3.new(1, 1, 1)
	b.Font = Enum.Font.GothamBold
	b.TextSize = 18
	b.Text = label
	b.AutoButtonColor = true
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, 8)
	c.Parent = b
	b.Parent = parent
	b.MouseButton1Click:Connect(onClick)
	return b
end

-- top bar: title + scenario buttons + mode buttons
local top = frame({ Size = UDim2.new(1, -24, 0, 112), Position = UDim2.fromOffset(12, 12) })
top.Parent = gui
text(top, "Oakland Flood Consequence Explorer  ·  West Oakland & waterfront", 22,
	{ Position = UDim2.fromOffset(14, 8), Size = UDim2.new(1, -28, 0, 28), Font = Enum.Font.GothamBold })
local scenRow = Instance.new("Frame")
scenRow.BackgroundTransparency = 1
scenRow.Position = UDim2.fromOffset(14, 44)
scenRow.Size = UDim2.new(0.55, 0, 0, 44)
scenRow.Parent = top
local sl = Instance.new("UIListLayout")
sl.FillDirection = Enum.FillDirection.Horizontal
sl.Padding = UDim.new(0, 6)
sl.Parent = scenRow
local modeRow = scenRow:Clone()
modeRow.Position = UDim2.new(0.55, 10, 0, 44)
modeRow.Size = UDim2.new(0.45, -24, 0, 44)
modeRow.Parent = top
text(top, "Sea-level rise above today's high tide", 14,
	{ Position = UDim2.fromOffset(14, 88), Size = UDim2.new(0.5, 0, 0, 18), TextColor3 = Color3.fromRGB(180, 190, 205) })

local scenButtons, modeButtons = {}, {}

-- left: stats panel
local statsPanel = frame({ Size = UDim2.fromOffset(380, 330), Position = UDim2.fromOffset(12, 136) })
statsPanel.Parent = gui
list(statsPanel, 4)
local statsTitle = text(statsPanel, "", 22, { Font = Enum.Font.GothamBold })
local statLines = {}
for n = 1, 6 do statLines[n] = text(statsPanel, "", 20, { LayoutOrder = n }) end
local hazardNote = text(statsPanel, "", 13, { LayoutOrder = 10, TextColor3 = Color3.fromRGB(180, 190, 205), Size = UDim2.new(1, 0, 0, 52) })

-- left: legend
local legend = frame({ Size = UDim2.fromOffset(380, 170), Position = UDim2.fromOffset(12, 476) })
legend.Parent = gui
list(legend, 4)

-- right: top priority list
local prio = frame({ Size = UDim2.fromOffset(400, 300), Position = UDim2.new(1, -412, 0, 136) })
prio.Parent = gui
list(prio, 4)

-- right: building info (click)
local info = frame({ Size = UDim2.fromOffset(400, 190), Position = UDim2.new(1, -412, 0, 446), Visible = false })
info.Parent = gui
list(info, 2)

-- bottom: viewpoints + walk toggle + disclaimer
local bottom = frame({ Size = UDim2.new(1, -24, 0, 88), Position = UDim2.new(0, 12, 1, -100) })
bottom.Parent = gui
local vpRow = scenRow:Clone()
vpRow.Position = UDim2.fromOffset(14, 8)
vpRow.Size = UDim2.new(1, -28, 0, 44)
vpRow.Parent = bottom
text(bottom, "Exploration tool, not an official hazard or evacuation map. Flood extents: ART Bay Shoreline Flood Explorer (BCDC); +5 ft uses ART's 5.5 ft map. Residents are estimates. Contaminated-site proximity is not exposure.",
	13, { Position = UDim2.fromOffset(14, 54), Size = UDim2.new(1, -28, 0, 30), TextColor3 = Color3.fromRGB(180, 190, 205) })

local function fmt(n)
	local s = tostring(math.floor(n + 0.5))
	local withCommas = s:reverse():gsub("(%d%d%d)", "%1,"):reverse():gsub("^,", "")
	return withCommas
end

local LEGENDS = {
	["Flood"] = { { C.floodShallow, "Flooded (shallow)" }, { C.floodDeep, "Flooded (deep, 2 m+)" }, { C.lowLying, "Below water level but protected (low-lying)" }, { C.roadImpassable, "Road impassable (> 15 cm)" }, { C.building, "Dry" } },
	["Cut off"] = { { C.cutOff, "Cut off from fire or medical services" }, { C.degraded, "Response time more than doubles" }, { C.floodShallow, "Flooded" }, { C.roadImpassable, "Road impassable" } },
	["Contamination"] = { { C.contam, "Within 100 m of a cleanup site near flooding" }, { C.floodShallow, "Flooded" }, { Color3.fromRGB(150, 150, 150), "Cleanup site (not near flooding)" } },
	["Priority"] = { { C.priorityHigh, "Highest priority tract" }, { C.priorityLow, "Lower priority" }, { C.buildingDim, "Not exposed / not ranked" } },
}

local function refreshPanels()
	local i = state.scenario
	local s = Stats.scenarios[i]
	statsTitle.Text = ("%s  ·  %s view"):format(Config.SCENARIO_LABELS[i], state.mode)
	statLines[1].Text = ("Residents affected:  %s"):format(fmt(s.residents_affected))
	statLines[2].Text = ("Buildings flooded:  %s"):format(fmt(s.buildings_flooded))
	statLines[3].Text = ("Critical facilities lost:  %d"):format(s.facilities_lost)
	statLines[4].Text = ("Residents cut off:  %s"):format(fmt(s.residents_cut_off))
	statLines[5].Text = ("Cleanup sites near flooding:  %d"):format(s.contaminated_sites_near_flooding)
	statLines[6].Text = ("Impassable road:  %.1f km"):format(s.road_km_impassable)
	hazardNote.Text = s.art_level_in and (("Hazard: ART %d-inch map%s. Water level %.2f m NAVD88."):format(
		s.art_level_in, s.art_level_in ~= 12 * s.slr_ft and " (ART has no 60-inch map)" or "", s.water_level_navd88_m))
		or "Hazard: LiDAR bathtub model (fallback)."

	for _, c in ipairs(legend:GetChildren()) do if c:IsA("GuiObject") then c:Destroy() end end
	text(legend, "Legend: " .. state.mode, 18, { Font = Enum.Font.GothamBold })
	for n, row in ipairs(LEGENDS[state.mode]) do
		local r = Instance.new("Frame")
		r.BackgroundTransparency = 1
		r.Size = UDim2.new(1, 0, 0, 22)
		r.LayoutOrder = n
		local sw = Instance.new("Frame")
		sw.Size = UDim2.fromOffset(18, 18)
		sw.BackgroundColor3 = row[1]
		sw.BorderSizePixel = 0
		sw.Parent = r
		text(r, row[2], 16, { Position = UDim2.fromOffset(26, -2), Size = UDim2.new(1, -26, 0, 22) })
		r.Parent = legend
	end

	for _, c in ipairs(prio:GetChildren()) do if c:IsA("GuiObject") then c:Destroy() end end
	text(prio, "Where help should start (" .. Config.SCENARIO_LABELS[i] .. ")", 18, { Font = Enum.Font.GothamBold })
	local tops = Stats.top_priority[Config.SCENARIOS[i]] or {}
	if #tops == 0 then
		text(prio, "No exposed tracts at this level.", 16, { LayoutOrder = 1 })
	end
	for n, t in ipairs(tops) do
		text(prio, ("%d. Tract %s (%s) · CES %d%%ile\n    %s flooded bldgs · %s residents · %s cut off"):format(
			t.rank, string.sub(t.tract_id, 6, 9) .. "." .. string.sub(t.tract_id, 10, 11), t.city, math.floor(t.ces_pctl),
			fmt(t.buildings_flooded), fmt(t.residents_affected), fmt(t.residents_cut_off)), 15,
			{ LayoutOrder = n, Size = UDim2.new(1, 0, 0, 42) })
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

for i, sid in ipairs(Config.SCENARIOS) do
	scenButtons[i] = button(scenRow, Config.SCENARIO_LABELS[i], 92, function()
		state.scenario = i
		apply()
	end)
end
for _, name in ipairs(Config.MODES) do
	modeButtons[name] = button(modeRow, name, 132, function()
		state.mode = name
		apply()
	end)
end

-- ------------------------------------------------------------------ camera
local W_STUDS, H_STUDS = m(7076), m(4492)
local flying = true
local camPos = Vector3.new(W_STUDS * 0.62, 2600, -H_STUDS * 0.15)
local yaw, pitch = math.rad(180), math.rad(-42)
local speedTiers = { 40, 120, 400, 1200 }
local speedIdx = 3
local vel = Vector3.zero

local VIEWS = {
	{ "Overview", Vector3.new(W_STUDS * 0.62, 2600, -H_STUDS * 0.05), 180, -42 },
	{ "West Oakland", Vector3.new(m(3300), 700, m(-1700)), 200, -35 },
	{ "Jack London", Vector3.new(m(4700), 420, m(-150)), 170, -30 },
	{ "Port", Vector3.new(m(1500), 900, m(-1800)), 235, -35 },
	{ "Fire Station 2", Vector3.new(m(4420), 300, m(-60)), 160, -30 },
}

local function goTo(v)
	flying = true
	camera.CameraType = Enum.CameraType.Scriptable
	camPos, yaw, pitch = v[2], math.rad(v[3]), math.rad(v[4])
end
for _, v in ipairs(VIEWS) do button(vpRow, v[1], 150, function() goTo(v) end) end
local walkBtn
walkBtn = button(vpRow, "Walk here", 150, function()
	flying = not flying
	local char = player.Character
	if not flying and char and char:FindFirstChild("HumanoidRootPart") then
		local params = RaycastParams.new()
		params.FilterDescendantsInstances = { city.Water, char }
		params.FilterType = Enum.RaycastFilterType.Exclude
		local hit = workspace:Raycast(camPos, Vector3.new(0, -5000, 0), params)
		local ground = hit and hit.Position or Vector3.new(camPos.X, 20, camPos.Z)
		char:PivotTo(CFrame.new(ground + Vector3.new(0, 6, 0)))
		camera.CameraType = Enum.CameraType.Custom
		walkBtn.Text = "Fly"
	else
		goTo({ "", camPos + Vector3.new(0, 150, 0), math.deg(yaw), -35 })
		walkBtn.Text = "Walk here"
	end
end)

UserInputService.InputChanged:Connect(function(input, gp)
	if not flying or gp then return end
	if input.UserInputType == Enum.UserInputType.MouseMovement and UserInputService:IsMouseButtonPressed(Enum.UserInputType.MouseButton2) then
		yaw -= input.Delta.X * 0.004
		pitch = math.clamp(pitch - input.Delta.Y * 0.004, math.rad(-89), math.rad(30))
	elseif input.UserInputType == Enum.UserInputType.MouseWheel then
		speedIdx = math.clamp(speedIdx + (input.Position.Z > 0 and 1 or -1), 1, #speedTiers)
	end
end)

RunService.RenderStepped:Connect(function(dt)
	if not flying then return end
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

-- ------------------------------------------------------------------ click a building
UserInputService.InputBegan:Connect(function(input, gp)
	if gp or input.UserInputType ~= Enum.UserInputType.MouseButton1 then return end
	local ray = camera:ViewportPointToRay(input.Position.X, input.Position.Y)
	local params = RaycastParams.new()
	params.FilterDescendantsInstances = { city.Buildings, markers }
	params.FilterType = Enum.RaycastFilterType.Include
	local hit = workspace:Raycast(ray.Origin, ray.Direction * 20000, params)
	for _, c in ipairs(info:GetChildren()) do if c:IsA("GuiObject") then c:Destroy() end end
	if not hit then info.Visible = false return end
	local p, i = hit.Instance, state.scenario
	info.Visible = true
	if p:GetAttribute("Kind") == "facility" then
		text(info, p.Name, 18, { Font = Enum.Font.GothamBold })
		text(info, ("Type: %s"):format(string.gsub(p:GetAttribute("Type"), "_", " ")), 16)
		text(info, flag(p:GetAttribute("Flooded") or "", i) and "FLOODED at this level" or "Not flooded at this level", 16)
		return
	elseif p:GetAttribute("Kind") == "site" then
		text(info, p.Name, 18, { Font = Enum.Font.GothamBold })
		text(info, ("%s · %s"):format(p:GetAttribute("Source"), p:GetAttribute("Category")), 15)
		text(info, flag(p:GetAttribute("NearFlood") or "", i) and "Within 100 m of flooding (proximity, not exposure)" or "Not near flooding at this level", 15)
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
end)

goTo(VIEWS[1])
apply()
