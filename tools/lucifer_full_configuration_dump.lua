-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
--[[
  ========================================================================
  LUCIFER MULTIBOT — MASTER CONFIGURATION & ALL-SETTINGS DUMPER (v3.0)
  Inspects and dumps EVERY setting, whether ACTIVE or INACTIVE:
    1. General Bot Settings & Safety Toggles
    2. Motion, Pathfinding & Delays
    3. Reconnect & Rest Intervals
    4. Collecting, Filtering & Gems Rules
    5. Trash List & Auto-Consume Settings
    6. Hardware Emulation & Login Profile
    7. All 18 Native Automation Engines (Full Internal Fields)
    8. Proxy Manager & Cooldown Configurations
    9. World Manager & Storage Routing
    10. Writes 'lucifer_full_configuration_dump.txt' & '.json'
  ========================================================================
--]]

local function safeGet(obj, field, default_val)
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

local function formatVal(v)
    if v == nil then return "nil (Not Set)" end
    local t = type(v)
    if t == "boolean" then
        return v and "TRUE [Active]" or "FALSE [Disabled]"
    elseif t == "table" then
        local count = 0
        for _ in pairs(v) do count = count + 1 end
        return string.format("table (Size: %d)", count)
    end
    return tostring(v)
end

local report_lines = {}
local json_dict = {}

local function logLine(text)
    table.insert(report_lines, text)
    print(text)
end

local function section(title)
    local bar = string.rep("=", 68)
    return "\n" .. bar .. "\n  " .. string.upper(title) .. "\n" .. bar
end

local function dumpFields(title, obj, fields, json_section)
    logLine(section(title))
    json_dict[json_section] = {}
    for _, f in ipairs(fields) do
        local val = safeGet(obj, f, nil)
        local formatted = formatVal(val)
        json_dict[json_section][f] = (type(val) == "table" and "table") or tostring(val)
        logLine(string.format("  * %-26s : %s", f, formatted))
    end
end

-- =========================================================================
-- START MASTER INSPECTION
-- =========================================================================

logLine(section("LUCIFER MULTIBOT — MASTER SETTINGS & CONFIGURATION DUMP"))

local bot = getBot()
if not bot then
    logLine("[FATAL ERROR] Bot object not available!")
    return
end

-- 1. BOT GENERAL TOGGLES
dumpFields("1. BOT GENERAL & SAFETY TOGGLES", bot, {
    "legit_mode",
    "anti_fire",
    "anti_toxic",
    "auto_reconnect",
    "auto_leave_on_mod",
    "auto_leave_on_admin",
    "auto_ban",
    "auto_accept",
    "auto_tutorial",
    "auto_expand_inventory",
    "leave_world_before_warp",
    "bypass_logon",
    "hide_gems",
    "ignore_gems",
    "ignore_essences",
    "dynamic_delay"
}, "bot_general")

-- 2. BOT DELAYS & TIMINGS
dumpFields("2. BOT DELAYS & TIMING CONFIGURATIONS", bot, {
    "reconnect_interval",
    "min_reconnect",
    "max_reconnect",
    "reconnect_multiplier",
    "random_reconnect",
    "maximum_ping",
    "auto_rest_mode",
    "rest_time",
    "rest_interval",
    "disconnect_on_rest",
    "move_range",
    "move_interval"
}, "bot_delays")

-- 3. COLLECTING & TRASHING
dumpFields("3. COLLECTING, GEMS & TRASHING RULES", bot, {
    "auto_collect",
    "collect_range",
    "collect_path_check",
    "collect_all",
    "object_collect_delay",
    "gem_limit",
    "auto_trash",
    "auto_consume",
    "consume_id",
    "consume_interval",
    "consumed_once"
}, "collect_trash")

-- Inspect Trash List Items
if getTrashList then
    local ok, tlist = pcall(getTrashList)
    if ok and tlist then
        local names = {}
        for _, id in pairs(tlist) do
            local iname = (getInfo and getInfo(id) and getInfo(id).name) or ("ID " .. tostring(id))
            table.insert(names, string.format("%s (%d)", iname, id))
        end
        logLine(string.format("  * %-26s : %s", "active_trash_list",
            (#names > 0 and table.concat(names, ", ")) or "None (Empty List)"))
    end
end

-- 4. LOGIN PROFILE & DEVICE EMULATION
local login = bot.getLogin and bot:getLogin()
if login then
    dumpFields("4. DEVICE EMULATION & LOGIN PROFILE", login, {
        "name",
        "mail",
        "platform_id",
        "country",
        "player_age",
        "mac",
        "rid",
        "vid",
        "aid",
        "gid",
        "filter_messages",
        "requested_name",
        "aat",
        "wk",
        "hash"
    }, "login_profile")
end

-- 5. AUTO FARM ENGINE
if bot.auto_farm then
    dumpFields("5. AUTO FARM ENGINE CONFIGURATION", bot.auto_farm, {
        "enabled",
        "id",
        "auto_break",
        "auto_place",
        "auto_remote",
        "auto_retrieve",
        "mag_x",
        "mag_y",
        "block_storage",
        "seed_storage"
    }, "auto_farm")
end

-- 6. ROTATION ENGINE
if bot.rotation then
    dumpFields("6. ROTATION ENGINE CONFIGURATION", bot.rotation, {
        "enabled",
        "status",
        "primary",
        "secondary",
        "pnb_world",
        "pnb_in_home",
        "harvest_until_level",
        "tiles",
        "one_by_one",
        "break_x",
        "break_y",
        "auto_fill",
        "seed_drop_amount",
        "harvest_roots",
        "ignore_plant",
        "auto_exchange",
        "visit_random_worlds",
        "auto_jammer",
        "auto_fossil",
        "auto_leave_on_player",
        "suppress_pack_storage",
        "suppress_seed_storage",
        "clear_objects",
        "auto_rest",
        "custom_position",
        "harvest_interval",
        "plant_interval",
        "break_interval",
        "warp_interval"
    }, "rotation")
end

-- 7. AUTO GEIGER ENGINE
if bot.auto_geiger then
    dumpFields("7. AUTO GEIGER ENGINE CONFIGURATION", bot.auto_geiger, {
        "enabled",
        "insta_path",
        "use_chocolate",
        "spread"
    }, "auto_geiger")
end

-- 8. AUTO SPAM ENGINE
if bot.auto_spam then
    dumpFields("8. AUTO SPAM ENGINE CONFIGURATION", bot.auto_spam, {
        "enabled",
        "messages",
        "interval",
        "random_interval",
        "auto_interval",
        "use_color",
        "show_emote",
        "randomizer"
    }, "auto_spam")
end

-- 9. AUTO FISH ENGINE
if bot.auto_fish then
    dumpFields("9. AUTO FISH ENGINE CONFIGURATION", bot.auto_fish, {
        "enabled",
        "world",
        "x",
        "y",
        "auto_trawler",
        "auto_drill",
        "auto_gemonade",
        "reward_storage",
        "item_storage",
        "auto_trash"
    }, "auto_fish")
end

-- 10. AUTO COOK ENGINE
if bot.auto_cook then
    dumpFields("10. AUTO COOK ENGINE CONFIGURATION", bot.auto_cook, {
        "enabled",
        "world",
        "x",
        "y",
        "interval",
        "is_cooking",
        "food_storage",
        "ingredient_storage"
    }, "auto_cook")
end

-- 11. AUTO PARKOUR ENGINE
if bot.auto_parkour then
    dumpFields("11. AUTO PARKOUR ENGINE CONFIGURATION", bot.auto_parkour, {
        "enabled",
        "limit",
        "block",
        "type"
    }, "auto_parkour")
end

-- 12. AUTO CRIME ENGINE
if bot.auto_crime then
    dumpFields("12. AUTO CRIME ENGINE CONFIGURATION", bot.auto_crime, {
        "enabled",
        "world",
        "tool_storage",
        "reward_storage",
        "auto_bbq",
        "auto_wave"
    }, "auto_crime")
end

-- 13. AUTO CARNIVAL ENGINE
if bot.auto_carnival then
    dumpFields("13. AUTO CARNIVAL ENGINE CONFIGURATION", bot.auto_carnival, {
        "enabled",
        "reward_storage",
        "ticket_storage",
        "selected_game",
        "auto_buy",
        "auto_trash"
    }, "auto_carnival")
end

-- 14. AUTO MESSAGE ENGINE
if bot.auto_message then
    dumpFields("14. AUTO MESSAGE ENGINE CONFIGURATION", bot.auto_message, {
        "enabled",
        "interval",
        "victim_uid",
        "uid_count",
        "growid_count",
        "ignore_admin",
        "loop_mode",
        "auto_sb",
        "anti_exit",
        "type"
    }, "auto_message")
end

-- 15. PROXY MANAGER
if getProxyManager then
    local pm = getProxyManager()
    if pm then
        dumpFields("15. PROXY MANAGER SETTINGS", pm, {
            "auto_switch",
            "switch_on_ban",
            "switch_on_block",
            "switch_on_shadow",
            "cooldown",
            "timeout",
            "main_ip_reference",
            "bypass_cooldown",
            "localize",
            "spread"
        }, "proxy_manager")
    end
end

-- 16. WORLD MANAGER
if getWorldManager then
    local wm = getWorldManager()
    if wm then
        logLine(section("16. WORLD MANAGER SETTINGS"))
        local farms = safeGet(wm, "worlds", {})
        local seeds = safeGet(wm, "seed_storages", {})
        local packs = safeGet(wm, "pack_storages", {})

        local farm_cnt = (type(farms) == "table" and #farms) or 0
        local seed_cnt = (type(seeds) == "table" and #seeds) or 0
        local pack_cnt = (type(packs) == "table" and #packs) or 0

        logLine(string.format("  * Managed Farms Count   : %d", farm_cnt))
        logLine(string.format("  * Seed Storages Count   : %d", seed_cnt))
        logLine(string.format("  * Pack Storages Count   : %d", pack_cnt))
    end
end

-- =========================================================================
-- SAVE TO DISK
-- =========================================================================
logLine(section("SAVING COMPLETE CONFIGURATION DUMP"))

local function toJson(val)
    local t = type(val)
    if t == "number" then return tostring(val)
    elseif t == "boolean" then return val and "true" or "false"
    elseif t == "string" then return '"' .. val:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n') .. '"'
    elseif t == "table" then
        local parts = {}
        for k, v in pairs(val) do
            table.insert(parts, '"' .. tostring(k) .. '":' .. toJson(v))
        end
        return "{" .. table.concat(parts, ",") .. "}"
    end
    return '"' .. tostring(val) .. '"'
end

local txt_out = "lucifer_full_configuration_dump.txt"
local json_out = "lucifer_full_configuration_dump.json"

if write then
    write(txt_out, table.concat(report_lines, "\n"))
    write(json_out, toJson(json_dict))
    logLine(string.format("  [OK] Master settings TXT saved  : %s", txt_out))
    logLine(string.format("  [OK] Master settings JSON saved : %s", json_out))
end

logLine(section("DUMP COMPLETED SUCCESSFULLY!"))
