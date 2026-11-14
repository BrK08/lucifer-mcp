-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
--[[
  ========================================================================
  LUCIFER MULTIBOT — IN-GAME COMPREHENSIVE DEBUGGER & CAPABILITY INSPECTOR
  Version: v2.1 (ASCII Pure / Smart Coordinates / Safe Execution)
  Target: Lucifer v2.88 p2 / Growtopia
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

local function separator(title)
    local line = string.rep("=", 65)
    if title then
        return "\n" .. line .. "\n  " .. string.upper(title) .. "\n" .. line
    end
    return line
end

local report_lines = {}
local function logLine(text)
    table.insert(report_lines, text)
    print(text)
end

logLine(separator("LUCIFER IN-GAME DEEP DIAGNOSTIC REPORT"))

-- -------------------------------------------------------------------------
-- 1. BOT ACCOUNT & SYSTEM STATUS
-- -------------------------------------------------------------------------
logLine(separator("1. BOT IDENTITY & ACCOUNT STATUS"))

local bot = getBot()
if not bot then
    logLine("[ERROR] Could not obtain Bot object via getBot()!")
    return
end

local b_name = safe(bot, "name", "Unknown")
local b_level = safe(bot, "level", 0)
local b_gems = safe(bot, "gem_count", 0)
local b_obtained_gems = safe(bot, "obtained_gem_count", 0)
local b_pearls = safe(bot, "pearl_count", 0)
local b_vouchers = safe(bot, "voucher_count", 0)
local b_status = safe(bot, "status", 0)
local b_google = safe(bot, "google_status", 0)
local b_ping = safe(bot, "getPing", 0)
local b_active_time = safe(bot, "getActiveTime", "N/A")
local b_secured = safe(bot, "is_account_secured", false)
local b_supporter = safe(bot, "isSupporter", false)

logLine(string.format("  - Bot GrowID         : %s", tostring(b_name)))
logLine(string.format("  - Account Level      : %s", tostring(b_level)))
logLine(string.format("  - Total Gems         : %s (Session Earned: %s)", tostring(b_gems), tostring(b_obtained_gems)))
logLine(string.format("  - Pearls / Vouchers  : %s / %s", tostring(b_pearls), tostring(b_vouchers)))
logLine(string.format("  - Ping to Server     : %s ms", tostring(b_ping)))
logLine(string.format("  - Bot Status Code    : %s", tostring(b_status)))
logLine(string.format("  - Google Status Code : %s", tostring(b_google)))
logLine(string.format("  - Account Secured    : %s", tostring(b_secured)))
logLine(string.format("  - Supporter Status   : %s", tostring(b_supporter)))
logLine(string.format("  - Active Playtime    : %s", tostring(b_active_time)))

-- -------------------------------------------------------------------------
-- 2. WORLD & POSITION INSPECTION
-- -------------------------------------------------------------------------
logLine(separator("2. CURRENT WORLD & COORDINATES"))

local world = (bot.getWorld and bot:getWorld()) or (getWorld and getWorld())
local world_name = world and safe(world, "name", "") or ""

if world_name == "" or world_name == "EXIT" then
    logLine("  [!] Bot is currently in WORLD SELECT MENU / MAIN MENU.")
    logLine("      Tip: Run bot:warp('START') to enter a world and inspect tiles.")
else
    local bx = safe(bot, "x", 0)
    local by = safe(bot, "y", 0)
    local raw_x = tonumber(bx) or 0
    local raw_y = tonumber(by) or 0
    -- In Lucifer v2.88 p2, bot.x and bot.y are already tile coordinates if <= 100
    local tile_x = (raw_x > 100) and math.floor(raw_x / 32) or raw_x
    local tile_y = (raw_y > 100) and math.floor(raw_y / 32) or raw_y

    logLine(string.format("  - Current World Name : %s", world_name))
    logLine(string.format("  - Bot Tile Position  : (%d, %d)", tile_x, tile_y))

    -- Inspect current tile
    local get_t = getTile or (world and world.getTile)
    if get_t then
        local t = get_t(tile_x, tile_y)
        if t then
            logLine(string.format("  - Standing On Tile   : FG=%s, BG=%s, Flags=%s",
                tostring(t.fg or 0), tostring(t.bg or 0), tostring(t.flags or 0)))
        end
    end

    -- Count floating objects
    local objs = (getObjects and getObjects()) or (world and world.getObjects and world:getObjects())
    if objs then
        local obj_count = 0
        local total_float_gems = 0
        for _, o in pairs(objs) do
            obj_count = obj_count + 1
            if o.id == 112 then
                total_float_gems = total_float_gems + (o.count or 1)
            end
        end
        logLine(string.format("  - Floating Objects   : %d items on ground (Gems: %d)", obj_count, total_float_gems))
    end
end

-- -------------------------------------------------------------------------
-- 3. INVENTORY DUMP
-- -------------------------------------------------------------------------
logLine(separator("3. INVENTORY INSPECTION"))

local inv = (bot.getInventory and bot:getInventory()) or (getInventory and getInventory())
if inv then
    local slot_count = safe(inv, "slotcount", 0)
    local empty_slots = safe(inv, "emptyslots", 0)
    local item_count = safe(inv, "itemcount", 0)

    logLine(string.format("  - Total Slots Available : %s", tostring(slot_count)))
    logLine(string.format("  - Empty Slots Remaining : %s", tostring(empty_slots)))
    logLine(string.format("  - Distinct Item Count   : %s", tostring(item_count)))

    local items = inv.getItems and inv:getItems()
    if items then
        logLine("  --- [Item List] ---")
        local idx = 0
        for _, it in pairs(items) do
            idx = idx + 1
            local iid = it.id or 0
            local icnt = it.count or 0
            local active_str = (it.isActive and " [EQUIPPED]") or ""

            local iname = "Item"
            if getInfo then
                local info = getInfo(iid)
                if info and info.name then iname = info.name end
            end

            logLine(string.format("    [%02d] ID: %-5d | Count: %-4d | %s%s", idx, iid, icnt, iname, active_str))
        end
    end
else
    logLine("  [!] Inventory object not available at this moment.")
end

-- -------------------------------------------------------------------------
-- 4. PLAYERS IN WORLD
-- -------------------------------------------------------------------------
logLine(separator("4. PLAYERS IN CURRENT WORLD"))

local players = (getPlayers and getPlayers()) or (world and world.getPlayers and world:getPlayers())
if players then
    local p_count = 0
    for _, p in pairs(players) do
        p_count = p_count + 1
        local pname = safe(p, "name", "Unknown")
        local pnet = safe(p, "netid", 0)
        local raw_px = tonumber(safe(p, "x", 0)) or 0
        local raw_py = tonumber(safe(p, "y", 0)) or 0
        local px = (raw_px > 100) and math.floor(raw_px / 32) or raw_px
        local py = (raw_py > 100) and math.floor(raw_py / 32) or raw_py
        logLine(string.format("    - Player: %-16s | NetID: %-5s | Pos: (%d, %d)", pname, tostring(pnet), px, py))
    end
    if p_count == 0 then
        logLine("    (No other players in world)")
    end
else
    logLine("    (Players list not available outside of active world)")
end

-- -------------------------------------------------------------------------
-- 5. NATIVE AUTOMATION ENGINES CHECK
-- -------------------------------------------------------------------------
logLine(separator("5. AUTOMATION ENGINES STATUS"))

local function checkAuto(name, obj)
    if not obj then return "Not Available" end
    local en = safe(obj, "enabled", false)
    return en and "ENABLED (Active)" or "DISABLED (Idle)"
end

logLine(string.format("  - Auto Farm     : %s", checkAuto("auto_farm", bot.auto_farm)))
logLine(string.format("  - Auto Geiger   : %s", checkAuto("auto_geiger", bot.auto_geiger)))
logLine(string.format("  - Auto Spam     : %s", checkAuto("auto_spam", bot.auto_spam)))
logLine(string.format("  - Auto Fish     : %s", checkAuto("auto_fish", bot.auto_fish)))
logLine(string.format("  - Auto Cook     : %s", checkAuto("auto_cook", bot.auto_cook)))
logLine(string.format("  - Auto Parkour  : %s", checkAuto("auto_parkour", bot.auto_parkour)))
logLine(string.format("  - Auto Collect  : %s", tostring(bot.auto_collect or false)))
logLine(string.format("  - Auto Trash    : %s", tostring(bot.auto_trash or false)))
logLine(string.format("  - Auto Mod-Leave: %s", tostring(bot.auto_leave_on_mod or false)))
logLine(string.format("  - Legit Mode    : %s", tostring(bot.legit_mode and safe(bot, "legit_mode", false) or false)))

-- -------------------------------------------------------------------------
-- 6. HTTP CLIENT & RELAY CONNECTIVITY TEST
-- -------------------------------------------------------------------------
logLine(separator("6. LOCAL MCP RELAY SERVER TEST (PORT 8829)"))

local relay_url = "http://127.0.0.1:8829/api/heartbeat"
local client = HttpClient.new()
client.url = relay_url
if client.timeout then client.timeout = 2 end
if client.setMethod and Method and Method.post then
    client:setMethod(Method.post)
else
    client.method = "POST"
end

local test_payload = string.format('{"name":"%s","status":"online","world":"%s","gem_count":%d,"level":%d}',
    b_name, world_name, tonumber(b_gems) or 0, tonumber(b_level) or 1)

client.content = test_payload
client.body = test_payload

local ok, resp = pcall(function() return client:request() end)
if ok and resp and resp.status then
    logLine(string.format("  [SUCCESS] Connected to MCP Relay Server! HTTP Status: %d", resp.status))
    if resp.body and #resp.body > 0 then
        logLine(string.format("  Server Response : %s", tostring(resp.body)))
    end
else
    logLine("  [INFO] MCP Relay Server (start.py) is not running on 127.0.0.1:8829.")
    logLine("         Run 'python start.py' in terminal to link with Discord and AI!")
end

-- -------------------------------------------------------------------------
-- 7. SAVE REPORT TO FILE
-- -------------------------------------------------------------------------
logLine(separator("7. SAVING REPORT"))

local full_text = table.concat(report_lines, "\n")
local save_path = "lucifer_ingame_report.txt"
if write then
    write(save_path, full_text)
    logLine(string.format("  [OK] Full report successfully written to: %s", save_path))
end

logLine(separator("DIAGNOSTIC TEST COMPLETE"))
