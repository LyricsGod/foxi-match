local fs = require "nixio.fs"
local sys = require "luci.sys"
local uci = require "luci.model.uci".cursor()

local PROG = "/etc/catfind-progress.json"

local function read_progress()
	local raw = fs.readfile(PROG) or ""
	return {
		level   = tonumber(raw:match('"level"%s*:%s*(%-?%d+)')) or 0,
		current = tonumber(raw:match('"current"%s*:%s*(%-?%d+)')) or 0,
		stamp   = tonumber(raw:match('"stamp"%s*:%s*(%-?%d+)')) or 0
	}
end

local function svc_stop()    sys.call("/etc/init.d/catfind stop >/dev/null 2>&1") end
local function svc_restart() sys.call("/etc/init.d/catfind restart >/dev/null 2>&1") end

local map = Map("catfind", translate("找猫游戏"),
	translate("逻辑推理小游戏：每行每列每个色块各有一只猫，且猫不能相邻。"))

local s = map:section(TypedSection, "catfind", translate("基本设置"))
s.anonymous = true
s.addremove = false

------------------------------------------------------------------------
-- 开关：写入即生效（普通“保存”也会触发）
------------------------------------------------------------------------
local e = s:option(Flag, "enabled", translate("启用游戏"),
	translate("关闭后立刻停止游戏服务并释放端口，不影响 LuCI 本身。"))
e.rmempty = false
function e.write(self, section, value)
	Flag.write(self, section, value)
	uci:commit("catfind")
	if value == "1" then svc_restart() else svc_stop() end
end

------------------------------------------------------------------------
-- 端口：写入即生效
------------------------------------------------------------------------
local p = s:option(Value, "port", translate("网页端口"),
	translate("游戏在独立端口运行，不影响 LuCI 的 80 端口。改完保存立即生效。"))
p.datatype = "port"
p.rmempty = false
p.default = "8088"
function p.write(self, section, value)
	local old = self:cfgvalue(section)
	Value.write(self, section, value)
	if tostring(old) ~= tostring(value) then
		uci:commit("catfind")
		if uci:get_bool("catfind", section, "enabled") then svc_restart() end
	end
end

local a = s:option(DummyValue, "_addr", translate("访问地址"))
function a.cfgvalue()
	local port = uci:get("catfind", "main", "port") or "8088"
	local host = luci.http.getenv("SERVER_NAME") or "192.168.2.1"
	return "http://" .. host .. ":" .. port .. "/"
end

local r = s:option(DummyValue, "_state", translate("运行状态"))
function r.cfgvalue()
	if not uci:get_bool("catfind", "main", "enabled") then
		return translate("已停止")
	end
	local port = uci:get("catfind", "main", "port") or "8088"
	local out = sys.exec("netstat -ltn 2>/dev/null | grep -c ':" .. port .. " '") or "0"
	if (tonumber(out) or 0) > 0 then
		return translate("运行中") .. " (:" .. port .. ")"
	end
	return translate("已启用，但端口未监听")
end

local c = s:option(DummyValue, "_cur", translate("当前进度"))
function c.cfgvalue()
	local d = read_progress()
	if d.level < 1 then return translate("暂无记录（还没在游戏里玩过）") end
	local cu = d.current
	if cu < 1 then cu = d.level end
	return translate("已解锁到第") .. " " .. d.level .. " " .. translate("关，上次停在第") .. " " .. cu .. " " .. translate("关")
end

------------------------------------------------------------------------
-- 跳关：页面内 JS 调 CGI，绕开 CBI 表单序列化
------------------------------------------------------------------------
local j = s:option(DummyValue, "_jump", translate("跳到指定关卡"),
	translate("填关卡号后点按钮，打开游戏就会直接进入该关（所有设备通用）。"))
j.rawhtml = true
function j.cfgvalue()
	return [[
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
  <input id="cf-lv" type="number" min="1" max="999" placeholder="关卡号"
         style="width:120px;padding:7px 10px;border:1px solid #d5d9e0;border-radius:6px;font-size:13px">
  <button type="button" id="cf-go"
          style="padding:7px 16px;border:0;border-radius:6px;background:#3d7cf5;color:#fff;font-size:13px;cursor:pointer">
    跳转到该关
  </button>
  <span id="cf-msg" style="font-size:12px;color:#3d7cf5"></span>
</div>
<script type="text/javascript">
(function(){
  var btn = document.getElementById('cf-go');
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = '1';
  btn.addEventListener('click', function(){
    var inp = document.getElementById('cf-lv');
    var msg = document.getElementById('cf-msg');
    var n = parseInt(inp && inp.value, 10);
    if (!n || n < 1) { msg.textContent = '请输入大于 0 的关卡号'; return; }
    msg.textContent = '设置中...';
    fetch('/cgi-bin/catfind-setlevel?level=' + n, { cache: 'no-store' })
      .then(function(r){ return r.json(); })
      .then(function(d){
        msg.textContent = d && d.ok ? ('已设为第 ' + n + ' 关，打开游戏即生效') : '设置失败';
        if (d && d.ok) setTimeout(function(){ location.reload(); }, 1200);
      })
      .catch(function(){ msg.textContent = '请求失败，请重试'; });
  });
})();
</script>]]
end

return map
