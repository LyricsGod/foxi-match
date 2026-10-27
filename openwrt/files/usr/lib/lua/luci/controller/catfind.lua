module("luci.controller.catfind", package.seeall)

function index()
	if not nixio.fs.access("/etc/config/catfind") then
		return
	end

	local page = entry({"admin", "services", "catfind"}, cbi("catfind"), _("找猫游戏"), 65)
	page.dependent = false
end
