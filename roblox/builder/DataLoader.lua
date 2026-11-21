-- ServerStorage.FloodBuilder.DataLoader (ModuleScript). Edit-mode build only.
-- Reads files from the local data server with throttling + one retry.
local HttpService = game:GetService("HttpService")
local Config = require(game:GetService("ReplicatedStorage").FloodViewer.Config)

local DataLoader = {}
local MIN_GAP = 0.14 -- stay under ~500 requests/min
local last = 0

function DataLoader.get(path)
	local url = path:match("^http") and path or (Config.DATA .. "/" .. path)
	-- cache-buster: Studio's HTTP layer can return a stale copy even with nocache = true
	url ..= (url:find("?", 1, true) and "&" or "?") .. "v=" .. tostring(os.time()) .. tostring(math.random(1e6))
	for attempt = 1, 2 do
		local wait = MIN_GAP - (os.clock() - last)
		if wait > 0 then task.wait(wait) end
		last = os.clock()
		local ok, res = pcall(HttpService.GetAsync, HttpService, url, true)
		if ok then return res end
		warn(("[DataLoader] %s failed (attempt %d): %s"):format(url, attempt, tostring(res)))
		task.wait(1)
	end
	error("[DataLoader] giving up on " .. url)
end

function DataLoader.json(path)
	return HttpService:JSONDecode(DataLoader.get(path))
end

return DataLoader
