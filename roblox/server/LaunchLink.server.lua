-- ServerScriptService.LaunchLink (Script)
-- Deep link from the FloodWatch website into the 3D world:
--   https://www.roblox.com/games/start?placeId=<placeId>&launchData=<h3 index>
-- e.g. launchData=8928308027bffff drops the player into that FloodWatch hex in walk mode.
-- (Only works once the experience is published and the player can access it.)
-- Studio testing: set workspace attribute TestLaunchHex = "<h3>" before pressing Play.
local Players = game:GetService("Players")

local function onPlayer(player)
	local hex = workspace:GetAttribute("TestLaunchHex")
	local ok, joinData = pcall(function() return player:GetJoinData() end)
	if ok and joinData and type(joinData.LaunchData) == "string" and #joinData.LaunchData > 0 then
		hex = joinData.LaunchData
	end
	if type(hex) == "string" and hex:match("^%x+$") and #hex <= 20 then
		player:SetAttribute("LaunchHex", hex)
	end
end

Players.PlayerAdded:Connect(onPlayer)
for _, p in ipairs(Players:GetPlayers()) do onPlayer(p) end
