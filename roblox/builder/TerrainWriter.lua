-- ServerStorage.FloodBuilder.TerrainWriter (ModuleScript). Edit-mode build only.
-- Writes the binary height/material tiles from pipeline/08b as a terrain "crust": a few
-- voxels below the surface plus a fractional top voxel for a smooth surface.
-- Tile layout: u16 cols, u16 rows, u16 h[rows*cols], u8 mat[rows*cols]; rows start at the
-- south edge. Cell (i, k): X in [4i, 4i+4], Z in [-4(k+1), -4k] studs.
local Config = require(game:GetService("ReplicatedStorage").FloodViewer.Config)
local DataLoader = require(script.Parent.DataLoader)

local TerrainWriter = {}
local CRUST = 2    -- full voxels below the top voxel
local SUB = 64     -- columns per WriteVoxels call (per axis)
local VOX = 4

local function writeBlock(terrain, i0, k0, cols, rows, hy, mats)
	-- hy[c][r] = surface height in studs; mats[c][r] = Enum.Material
	local vmin, vmax = math.huge, -math.huge
	for c = 1, cols do
		for r = 1, rows do
			local v = math.floor(hy[c][r] / VOX)
			if v < vmin then vmin = v end
			if v > vmax then vmax = v end
		end
	end
	vmin -= CRUST
	local ny = vmax - vmin + 1
	local M, O = table.create(cols), table.create(cols)
	local air = Enum.Material.Air
	-- X = i (east), Z: region min Z is the north edge of the block (k0 + rows - 1)
	for c = 1, cols do
		local mc, oc = table.create(ny), table.create(ny)
		for y = 1, ny do
			local my, oy = table.create(rows), table.create(rows)
			for zi = 1, rows do
				-- zi = 1 is the northernmost row of this block
				local r = rows - zi + 1
				local hs = hy[c][r]
				local top = math.floor(hs / VOX)
				local vy = vmin + y - 1
				if vy < top - CRUST or vy > top then
					my[zi], oy[zi] = air, 0
				elseif vy < top then
					my[zi], oy[zi] = mats[c][r], 1
				else
					local f = (hs - top * VOX) / VOX
					my[zi], oy[zi] = mats[c][r], math.clamp(f, 0.05, 1)
				end
			end
			mc[y], oc[y] = my, oy
		end
		M[c], O[c] = mc, oc
	end
	local minV = Vector3.new(i0 * VOX, vmin * VOX, -(k0 + rows) * VOX)
	local maxV = Vector3.new((i0 + cols) * VOX, (vmax + 1) * VOX, -k0 * VOX)
	terrain:WriteVoxels(Region3.new(minV, maxV), VOX, M, O)
end

-- Writes one tile file. Returns number of columns written.
function TerrainWriter.writeTile(ti, tk, meta)
	local raw = DataLoader.get(("%s/tile_%d_%d.bin"):format(meta.dir, ti, tk))
	local b = buffer.fromstring(raw)
	local cols, rows = buffer.readu16(b, 0), buffer.readu16(b, 2)
	local n = cols * rows
	local hOff, mOff = 4, 4 + 2 * n
	local span = meta.zmax_m - meta.zmin_m
	local terrain = workspace.Terrain
	local mats = Config.TERRAIN_MATERIALS
	local baseI, baseK = ti * meta.tile_cols, tk * meta.tile_cols
	for sk = 0, rows - 1, SUB do
		for si = 0, cols - 1, SUB do
			local bc, br = math.min(SUB, cols - si), math.min(SUB, rows - sk)
			local hy, mm = table.create(bc), table.create(bc)
			for c = 1, bc do
				local hc, mc = table.create(br), table.create(br)
				for r = 1, br do
					local idx = (sk + r - 1) * cols + (si + c - 1)
					local v = buffer.readu16(b, hOff + 2 * idx)
					hc[r] = Config.m(meta.zmin_m + v / 65535 * span)
					mc[r] = mats[buffer.readu8(b, mOff + idx) + 1]
				end
				hy[c], mm[c] = hc, mc
			end
			writeBlock(terrain, baseI + si, baseK + sk, bc, br, hy, mm)
			task.wait()
		end
	end
	return n
end

-- Resume-aware: tiles are processed in a fixed order; progress lives on the City folder.
-- region (optional) = {i0, i1, k0, k1} tile index bounds for a sub-area test.
function TerrainWriter.run(meta, city, region)
	local list = {}
	for tk = 0, meta.tiles_k - 1 do
		for ti = 0, meta.tiles_i - 1 do
			if not region or (ti >= region[1] and ti <= region[2] and tk >= region[3] and tk <= region[4]) then
				table.insert(list, { ti, tk })
			end
		end
	end
	local key = region and "TerrainNextSub" or "TerrainNext"
	local start = city:GetAttribute(key) or 1
	for n = start, #list do
		local t = list[n]
		TerrainWriter.writeTile(t[1], t[2], meta)
		city:SetAttribute(key, n + 1)
		city:SetAttribute("Progress", ("terrain %d/%d"):format(n, #list))
	end
	city:SetAttribute(region and "TerrainSubDone" or "TerrainDone", true)
end

return TerrainWriter
