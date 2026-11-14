-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
--[[
  ========================================================================
  LUCIFER MULTIBOT — ULTIMATE IN-GAME DEEP API & OBJECT DUMPER
  Version: v3.0 (Deep Metatable & Runtime Introspection)
  Target: Lucifer v2.88 p2 / Active World Session
  ========================================================================
  Since the bot is actively inside a world (ASDASDASDASVASD), this script
  instantiates and deeply inspects every live object that CANNOT be inspected
  offline:
    1. World Object & all methods / fields
    2. Tile Object & all methods / flags / states
    3. Player Object (NetAvatar) & clothes / coords / states
    4. InventoryItem & Inventory methods
    5. ItemDescription (Item Database schema for Dirt, Seeds, Tools)
    6. NetObject (Floating items on ground)
    7. Variant & VariantList methods & types
    8. GameUpdatePacket & Raw Packet builders
    9. TileExtra (Locks, Signs, Doors, Trees)
    10. Writes both 'lucifer_ultimate_api_dump.txt' & '.json'
--]]

local report_lines = {}
local json_data = {
    metadata = {
        title = "Lucifer Multibot Ultimate In-Game API Dump",
        version = "v3.0",
        timestamp = os.time and os.time() or 0
    },
    world_class = {},
    tile_class = {},
    player_class = {},
    inventory_class = {},
    item_description_class = {},
    net_object_class = {},
    variantlist_class = {},
    game_update_packet_class = {}
}

local function log(text)
    table.insert(report_lines, text)
    print(text)
end

local function header(title)
    local bar = string.rep("=", 68)
    return "\n" .. bar .. "\n  " .. string.upper(title) .. "\n" .. bar
end

local function inspectUserdata(obj, name, target_dict)
    if not obj then return end
    log(string.format("\n--- [INSPECTING OBJECT: %s] ---", name))

    local mt = (debug and debug.getmetatable and debug.getmetatable(obj)) or getmetatable(obj)
    local found = {}

    -- Check direct pairs if accessible
    pcall(function()
        for k, v in pairs(obj) do
            found[tostring(k)] = type(v)
        end
    end)

    -- Check metatable __index table
    if mt and type(mt.__index) == "table" then
        for k, v in pairs(mt.__index) do
            found[tostring(k)] = type(v)
        end
    end

    -- Probe common candidate methods and properties
    local candidate_methods = {
        -- World
        "name", "width", "height", "owner_id", "owner_name", "weather", "hasAccess",
        "getTile", "getTiles", "getTilesSafe", "getPlayers", "getObjects", "findPath",
        "tiles", "players", "objects",
        -- Tile
        "fg", "bg", "flags", "x", "y", "ready", "growth", "canHarvest", "canPlant",
        "isSolid", "hasExtra", "extra", "getExtra", "reset",
        -- Player
        "name", "netid", "userid", "country", "x", "y", "clothes", "invis", "mstate",
        "smstate", "facing_left", "punch_range", "is_mod", "is_friend", "titleIcon",
        -- ItemDescription
        "id", "name", "rarity", "growTime", "breakHits", "actionType", "collisionType",
        "clothingType", "seedBase", "seedOverlay", "treeBase", "treeLeaves",
        "seedColor", "seedOverlayColor", "ingredient",
        -- InventoryItem
        "id", "count", "isActive",
        -- NetObject
        "id", "count", "x", "y", "oid", "flags",
        -- VariantList
        "size", "get", "append", "clear", "print", "serialize"
    }

    for _, prop in ipairs(candidate_methods) do
        if found[prop] == nil then
            local ok, val = pcall(function() return obj[prop] end)
            if ok and val ~= nil then
                found[prop] = type(val)
                if type(val) == "function" then
                    found[prop] = "method"
                end
            end
        end
    end

    -- Log and record results
    for k, v in pairs(found) do
        target_dict[k] = v
        log(string.format("  * %-24s : %s", name .. ":" .. k, v))
    end
end

-- =========================================================================
-- START ULTIMATE INTROSPECTION
-- =========================================================================

log(header("LUCIFER V2.88 P2 — ULTIMATE IN-GAME RUNTIME DUMP (v3.0)"))

local bot = getBot()
if not bot then
    log("[FATAL ERROR] Bot object is nil!")
    return
end

-- 1. INSPECT WORLD OBJECT
local world = (bot.getWorld and bot:getWorld()) or (getWorld and getWorld())
if world then
    inspectUserdata(world, "world", json_data.world_class)
else
    log("[!] World object is nil. Warping into world first is recommended.")
end

-- 2. INSPECT TILE OBJECT
local tile = nil
local bx = tonumber(bot.x or 0) or 0
local by = tonumber(bot.y or 0) or 0
local tx = (bx > 100) and math.floor(bx / 32) or bx
local ty = (by > 100) and math.floor(by / 32) or by

if getTile then
    tile = getTile(tx, ty)
elseif world and world.getTile then
    tile = world:getTile(tx, ty)
end

if tile then
    inspectUserdata(tile, "tile", json_data.tile_class)

    -- If tile has extra, inspect TileExtra
    local extra = tile.extra or (tile.getExtra and tile:getExtra())
    if extra then
        json_data.tile_extra_class = {}
        inspectUserdata(extra, "tile_extra", json_data.tile_extra_class)
    end
else
    log("[!] Could not obtain active Tile object at (" .. tx .. ", " .. ty .. ")")
end

-- 3. INSPECT PLAYER OBJECT (LOCAL AVATAR)
local player = nil
if getLocal then player = getLocal() end
if not player and getPlayers then
    local plist = getPlayers()
    if plist and #plist > 0 then player = plist[1] end
end

if player then
    inspectUserdata(player, "player", json_data.player_class)

    -- Inspect Clothes sub-object
    local clothes = player.clothes
    if clothes then
        json_data.clothes_class = {}
        inspectUserdata(clothes, "clothes", json_data.clothes_class)
    end
else
    log("[!] Player object could not be retrieved.")
end

-- 4. INSPECT INVENTORY & INVENTORY ITEM
local inv = (bot.getInventory and bot:getInventory()) or (getInventory and getInventory())
if inv then
    inspectUserdata(inv, "inventory", json_data.inventory_class)

    local items = inv.getItems and inv:getItems()
    if items and #items > 0 then
        local first_item = items[1]
        inspectUserdata(first_item, "inventory_item", json_data.item_description_class)
    end
end

-- 5. INSPECT ITEM DESCRIPTION (ITEM DATABASE OBJECT)
if getInfo then
    local dirt_info = getInfo(2) -- Dirt
    if dirt_info then
        inspectUserdata(dirt_info, "item_info", json_data.item_description_class)
    end
end

-- 6. INSPECT NETOBJECT (FLOATING ITEM)
local objs = (getObjects and getObjects()) or (world and world.getObjects and world:getObjects())
if objs and #objs > 0 then
    inspectUserdata(objs[1], "net_object", json_data.net_object_class)
else
    log("  [INFO] No floating objects on ground right now. NetObject candidate logged.")
end

-- 7. INSPECT VARIANTLIST
if variantlist and variantlist.new then
    local ok, vl = pcall(function() return variantlist.new() end)
    if ok and vl then
        inspectUserdata(vl, "variantlist", json_data.variantlist_class)
    end
end

-- 8. INSPECT GAME UPDATE PACKET
if GameUpdatePacket and GameUpdatePacket.new then
    local ok, gup = pcall(function() return GameUpdatePacket.new() end)
    if ok and gup then
        inspectUserdata(gup, "game_update_packet", json_data.game_update_packet_class)
    end
end

-- =========================================================================
-- SAVE JSON AND TXT REPORTS
-- =========================================================================
log(header("SAVING ULTIMATE DUMP TO FILES"))

-- Simple JSON encoder
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

local txt_path = "lucifer_ultimate_api_dump.txt"
local json_path = "lucifer_ultimate_api_dump.json"

if write then
    local full_text = table.concat(report_lines, "\n")
    write(txt_path, full_text)
    write(json_path, toJson(json_data))
    log(string.format("  [OK] Deep TXT dump saved to  : %s", txt_path))
    log(string.format("  [OK] Deep JSON dump saved to : %s", json_path))
else
    log("[!] write() function not available.")
end

log(header("DUMP COMPLETED SUCCESSFULLY!"))
