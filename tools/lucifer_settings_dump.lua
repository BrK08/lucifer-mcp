-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
--[[
  ========================================================================
  LUCIFER MULTIBOT — SETTINGS & CONFIGURATION DUMPER (v1.0)
  Inspects every active bot setting, delay, security toggle, and automation config
  ========================================================================
--]]

local function safe(obj, field, default_val)
    if not obj then return default_val end
    local val = obj[field]
    if type(val) == "function" then
        local ok, res = pcall(function() return obj[field](obj) end)
        if ok and res ~= nil then return res end
    elseif val ~= nil then
        return val
    end
    return default_val
end

local function header(title)
    local bar = string.rep("=", 68)
    return "\n" .. bar .. "\n  " .. string.upper(title) .. "\n" .. bar
end

local lines = {}
local function log(text)
    table.insert(lines, text)
    print(text)
end

local bot = getBot()
if not bot then
    print("[ERROR] Bot not found!")
    return
end

log(header("LUCIFER ACTIVE BOT SETTINGS & CONFIGURATION REPORT"))

-- 1. BOT SECURITY & BEHAVIOR SETTINGS
log("\n[1. GENERAL & BEHAVIOR SETTINGS]")
log(string.format("  * Legit Mode            : %s", tostring(safe(bot, "legit_mode", false))))
log(string.format("  * Anti-Fire             : %s", tostring(safe(bot, "anti_fire", false))))
log(string.format("  * Anti-Toxic            : %s", tostring(safe(bot, "anti_toxic", false))))
log(string.format("  * Auto Reconnect        : %s", tostring(safe(bot, "auto_reconnect", false))))
log(string.format("  * Auto Leave On Mod     : %s", tostring(safe(bot, "auto_leave_on_mod", false))))
log(string.format("  * Auto Leave On Admin   : %s", tostring(safe(bot, "auto_leave_on_admin", false))))
log(string.format("  * Auto Ban On Join      : %s", tostring(safe(bot, "auto_ban", false))))
log(string.format("  * Auto Accept Trades    : %s", tostring(safe(bot, "auto_accept", false))))
log(string.format("  * Auto Tutorial Run     : %s", tostring(safe(bot, "auto_tutorial", false))))
log(string.format("  * Auto Expand Inventory : %s", tostring(safe(bot, "auto_expand_inventory", false))))
log(string.format("  * Leave Before Warp     : %s", tostring(safe(bot, "leave_world_before_warp", false))))

-- 2. RECONNECT & REST DELAYS
log("\n[2. DELAYS, REST & TIMING SETTINGS]")
log(string.format("  * Reconnect Interval    : %s ms", tostring(safe(bot, "reconnect_interval", 0))))
log(string.format("  * Dynamic Delay Active  : %s", tostring(safe(bot, "dynamic_delay", false))))
log(string.format("  * Auto Rest Mode Active : %s", tostring(safe(bot, "auto_rest_mode", false))))
log(string.format("  * Rest Duration (Time)  : %s sec", tostring(safe(bot, "rest_time", 0))))
log(string.format("  * Rest Interval         : %s sec", tostring(safe(bot, "rest_interval", 0))))
log(string.format("  * Disconnect On Rest    : %s", tostring(safe(bot, "disconnect_on_rest", false))))
log(string.format("  * Maximum Ping Allowed  : %s ms", tostring(safe(bot, "maximum_ping", 0))))

-- 3. COLLECT & GEMS SETTINGS
log("\n[3. COLLECTING & GEMS SETTINGS]")
log(string.format("  * Auto Collect          : %s", tostring(safe(bot, "auto_collect", false))))
log(string.format("  * Collect Range         : %s tiles", tostring(safe(bot, "collect_range", 2))))
log(string.format("  * Collect Path Check    : %s", tostring(safe(bot, "collect_path_check", false))))
log(string.format("  * Collect All Mode      : %s", tostring(safe(bot, "collect_all", false))))
log(string.format("  * Object Collect Delay  : %s ms", tostring(safe(bot, "object_collect_delay", 0))))
log(string.format("  * Ignore Gems           : %s", tostring(safe(bot, "ignore_gems", false))))
log(string.format("  * Ignore Essences       : %s", tostring(safe(bot, "ignore_essences", false))))
log(string.format("  * Hide Gems On Screen   : %s", tostring(safe(bot, "hide_gems", false))))
log(string.format("  * Gem Limit (Cap)       : %s", tostring(safe(bot, "gem_limit", 0))))

-- 4. TRASH & CONSUMABLE SETTINGS
log("\n[4. TRASH & CONSUMABLE SETTINGS]")
log(string.format("  * Auto Trash Active     : %s", tostring(safe(bot, "auto_trash", false))))
log(string.format("  * Auto Consume Active   : %s", tostring(safe(bot, "auto_consume", false))))
log(string.format("  * Consume Item ID       : %s", tostring(safe(bot, "consume_id", 0))))
log(string.format("  * Consume Interval      : %s ms", tostring(safe(bot, "consume_interval", 0))))

if getTrashList then
    local ok, tlist = pcall(getTrashList)
    if ok and tlist then
        local ids = {}
        for _, id in pairs(tlist) do table.insert(ids, tostring(id)) end
        log(string.format("  * Active Trash List IDs : %s", (#ids > 0 and table.concat(ids, ", ")) or "(Empty)"))
    end
end

-- 5. LOGIN & DEVICE EMULATION SETTINGS
log("\n[5. DEVICE EMULATION & LOGIN PROFILE]")
local login = bot.getLogin and bot:getLogin()
if login then
    log(string.format("  * Account Name          : %s", tostring(safe(login, "name", "N/A"))))
    log(string.format("  * MAC Address           : %s", tostring(safe(login, "mac", "N/A"))))
    log(string.format("  * RID String            : %s", tostring(safe(login, "rid", "N/A"))))
    log(string.format("  * Platform ID           : %s", tostring(safe(login, "platform_id", 0))))
    log(string.format("  * Country Code          : %s", tostring(safe(login, "country", "N/A"))))
    log(string.format("  * Player Age            : %s", tostring(safe(login, "player_age", "N/A"))))
end

-- 6. PROXY MANAGER SETTINGS
if getProxyManager then
    local pm = getProxyManager()
    if pm then
        log("\n[6. PROXY MANAGER SETTINGS]")
        log(string.format("  * Auto Switch Proxies   : %s", tostring(safe(pm, "auto_switch", false))))
        log(string.format("  * Switch On Ban         : %s", tostring(safe(pm, "switch_on_ban", false))))
        log(string.format("  * Switch On Block (13)  : %s", tostring(safe(pm, "switch_on_block", false))))
        log(string.format("  * Switch On Shadow Ban  : %s", tostring(safe(pm, "switch_on_shadow", false))))
        log(string.format("  * Proxy Cooldown Time   : %s sec", tostring(safe(pm, "cooldown", 0))))
    end
end

-- 7. WORLD MANAGER (ROTATION) SETTINGS
if getWorldManager then
    local wm = getWorldManager()
    if wm then
        log("\n[7. WORLD MANAGER SETTINGS]")
        local f_worlds = safe(wm, "worlds", {})
        log(string.format("  * Managed Worlds Count  : %s", tostring(type(f_worlds) == "table" and #f_worlds or 0)))
    end
end

log(header("SETTINGS INSPECTION COMPLETE"))

if write then
    write("lucifer_active_settings.txt", table.concat(lines, "\n"))
    print("\n[OK] Settings report saved to: lucifer_active_settings.txt")
end
