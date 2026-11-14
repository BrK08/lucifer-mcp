--[[
  LUCIFER MULTIBOT -- MCP & DISCORD BRIDGE v2.5
  Compatible with Lucifer v1.8, v2.32, v2.54, v2.86, v2.88 p2
  Multi-Tenant Token Support + Full Human-Equivalent API + Sync Eval Capture

  NOTE: PURE 7-BIT ASCII STRINGS ONLY. NO NON-ASCII OR TURKISH CHARACTERS.

  SETUP:
  1) Start the Lucifer MCP / Discord server.
  2) In Lucifer Lua Script Tab, execute:
     local c = HttpClient.new(); c.url = "http://127.0.0.1:8829/bridge.lua"; local r = c:request(); load(r and r.body or c.content)()
--]]

local SERVER_URL = "http://127.0.0.1:8829"
local OWNER_TOKEN = ""
if OWNER_TOKEN == "" then
    OWNER_TOKEN = tostring(_G.LUCIFER_SECRET or _G.LUCIFER_KEY or _G.OWNER_TOKEN or "")
end
local RELAY_URL = SERVER_URL
local HEARTBEAT_INTERVAL_MS = 1500

-- =========================================================================
-- Lightweight Embedded JSON Serializer & Parser
-- =========================================================================
local JSON = {}

function JSON.encode(val)
    local t = type(val)
    if t == "nil" then
        return "null"
    elseif t == "boolean" then
        return val and "true" or "false"
    elseif t == "number" then
        if val ~= val or val == math.huge or val == -math.huge then
            return "0"
        end
        return tostring(val)
    elseif t == "string" then
        local escaped = val:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
        return '"' .. escaped .. '"'
    elseif t == "table" then
        local is_array = true
        local max_i = 0
        for k, _ in pairs(val) do
            if type(k) ~= "number" or k <= 0 or math.floor(k) ~= k then
                is_array = false
                break
            end
            if k > max_i then max_i = k end
        end
        if is_array then
            local parts = {}
            for i = 1, max_i do
                parts[i] = JSON.encode(val[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(val) do
                table.insert(parts, JSON.encode(tostring(k)) .. ":" .. JSON.encode(v))
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return '"' .. tostring(val) .. '"'
end

local function _json_skip_ws(str, pos)
    return str:match("^%s*()", pos)
end

local _json_parse_val

local function _json_parse_str(str, pos)
    local c = str:sub(pos, pos)
    if c ~= '"' then return nil, pos end
    local res = {}
    local p = pos + 1
    local len = #str
    while p <= len do
        local ch = str:sub(p, p)
        if ch == '"' then
            return table.concat(res), p + 1
        elseif ch == '\\' then
            p = p + 1
            local esc = str:sub(p, p)
            if esc == "n" then table.insert(res, "\n")
            elseif esc == "r" then table.insert(res, "\r")
            elseif esc == "t" then table.insert(res, "\t")
            elseif esc == '"' then table.insert(res, '"')
            elseif esc == '\\' then table.insert(res, '\\')
            elseif esc == '/' then table.insert(res, '/')
            else table.insert(res, esc) end
        else
            table.insert(res, ch)
        end
        p = p + 1
    end
    return nil, pos
end

local function _json_parse_num(str, pos)
    local num_str = str:match("^-?%d+%.?%d*[eE]?[+-]?%d*", pos)
    if num_str and #num_str > 0 then
        return tonumber(num_str), pos + #num_str
    end
    return nil, pos
end

local function _json_parse_arr(str, pos)
    local arr = {}
    local p = _json_skip_ws(str, pos + 1)
    if str:sub(p, p) == "]" then return arr, p + 1 end
    while p <= #str do
        local val, next_p = _json_parse_val(str, p)
        table.insert(arr, val)
        p = _json_skip_ws(str, next_p)
        local sep = str:sub(p, p)
        if sep == "]" then return arr, p + 1
        elseif sep == "," then p = _json_skip_ws(str, p + 1)
        else return nil, p end
    end
    return nil, pos
end

local function _json_parse_obj(str, pos)
    local obj = {}
    local p = _json_skip_ws(str, pos + 1)
    if str:sub(p, p) == "}" then return obj, p + 1 end
    while p <= #str do
        local key, next_p = _json_parse_str(str, p)
        if not key then return nil, p end
        p = _json_skip_ws(str, next_p)
        if str:sub(p, p) ~= ":" then return nil, p end
        p = _json_skip_ws(str, p + 1)
        local val, after_val = _json_parse_val(str, p)
        obj[key] = val
        p = _json_skip_ws(str, after_val)
        local sep = str:sub(p, p)
        if sep == "}" then return obj, p + 1
        elseif sep == "," then p = _json_skip_ws(str, p + 1)
        else return nil, p end
    end
    return nil, pos
end

function _json_parse_val(str, pos)
    pos = _json_skip_ws(str, pos)
    local c = str:sub(pos, pos)
    if c == "{" then return _json_parse_obj(str, pos)
    elseif c == "[" then return _json_parse_arr(str, pos)
    elseif c == '"' then return _json_parse_str(str, pos)
    elseif str:sub(pos, pos + 3) == "true" then return true, pos + 4
    elseif str:sub(pos, pos + 4) == "false" then return false, pos + 5
    elseif str:sub(pos, pos + 3) == "null" then return nil, pos + 4
    else return _json_parse_num(str, pos) end
end

function JSON.decode(s)
    if not s or #s == 0 then return nil end
    local ok, val = pcall(function()
        local res, p = _json_parse_val(s, 1)
        return res
    end)
    if ok and val ~= nil then return val end

    local str = s:gsub('%[', '{'):gsub('%]', '}')
    str = str:gsub('null', 'nil')
    str = str:gsub('"([^"]+)"%s*:', '["%1"]=')
    local fn = load("return " .. str)
    if fn then
        local fok, fres = pcall(fn)
        if fok then return fres end
    end
    return nil
end

-- =========================================================================
-- Helper: Safe Property & Method Caller + HTTP Transport
-- =========================================================================

local function safeCall(obj, field, default_val)
    if not obj then return default_val end
    local ok_idx, val = pcall(function() return obj[field] end)
    if ok_idx and type(val) == "function" then
        local ok1, res1 = pcall(function() return obj[field](obj) end)
        if ok1 and res1 ~= nil then return res1 end
        local ok2, res2 = pcall(function() return obj[field]() end)
        if ok2 and res2 ~= nil then return res2 end
    elseif ok_idx and val ~= nil then
        return val
    end
    return default_val
end

local function safeSet(obj, key, val)
    if not obj then return false end
    local ok = pcall(function()
        obj[key] = val
    end)
    return ok
end

local function httpPostJson(endpoint, tbl)
    local client = HttpClient.new()
    local json_str = JSON.encode(tbl)
    pcall(function()
        client.headers = { ["Content-Type"] = "application/json" }
    end)
    pcall(function()
        if Method and Method.post then
            client.method = Method.post
            if client.setMethod then
                client:setMethod(Method.post)
            end
        else
            client.method = "POST"
        end
    end)
    client.url = SERVER_URL .. endpoint
    client.content = json_str
    pcall(function() client.body = json_str end)
    local ok, response = pcall(function() return client:request() end)
    return ok, response
end

local function getStatusName(status_val)
    if type(status_val) == "string" then
        local lower = status_val:lower()
        if lower == "online" or status_val == "94" or status_val == "1" or status_val == "23" or lower:find("online") then
            return "online"
        end
        return status_val
    end
    local num = tonumber(status_val) or 0
    if num == 94 or num == 1 or num == 23 then
        return "online"
    end
    if not BotStatus then return tostring(status_val or "unknown") end
    for k, v in pairs(BotStatus) do
        if v == status_val then return tostring(k):lower() end
    end
    return tostring(status_val or "unknown")
end

local function getCaptchaName(cap_val)
    if type(cap_val) == "string" then return cap_val end
    if not CaptchaStatus then return tostring(cap_val or "unknown") end
    for k, v in pairs(CaptchaStatus) do
        if v == cap_val then return tostring(k) end
    end
    return tostring(cap_val or "unknown")
end

-- =========================================================================
-- Synchronous Result Reporting & Lua Capture
-- =========================================================================

local _pending_results = {}

local function _recordResult(res_tbl)
    if not res_tbl or not res_tbl.cmd_id or #tostring(res_tbl.cmd_id) == 0 then
        return
    end
    local ok_http, resp = httpPostJson("/api/command_result", res_tbl)
    if not ok_http or not resp then
        table.insert(_pending_results, res_tbl)
        if #_pending_results > 50 then
            table.remove(_pending_results, 1)
        end
    end
end

local function _execLuaWithCapture(code_str, target_bot)
    local logs_buf = {}
    local total_chars = 0
    local orig_print = _G.print

    _G.print = function(...)
        local parts = {}
        local n = select("#", ...)
        for i = 1, n do
            table.insert(parts, tostring(select(i, ...)))
        end
        local line = table.concat(parts, "\t")
        if total_chars < 16000 then
            table.insert(logs_buf, line)
            total_chars = total_chars + #line + 1
        end
        if orig_print then
            pcall(orig_print, ...)
        end
    end

    local ok = false
    local ret_val = nil
    local err_msg = nil

    local chunk, compile_err = load(code_str)
    if not chunk then
        err_msg = "Syntax error: " .. tostring(compile_err)
    else
        local packed = { pcall(chunk) }
        ok = packed[1]
        if ok then
            if #packed == 2 then
                ret_val = packed[2]
            elseif #packed > 2 then
                local multi = {}
                for i = 2, #packed do
                    table.insert(multi, packed[i])
                end
                ret_val = multi
            end
        else
            err_msg = tostring(packed[2])
        end
    end

    _G.print = orig_print

    local serialized_ret = ret_val
    local rt = type(ret_val)
    if rt ~= "nil" and rt ~= "boolean" and rt ~= "number" and rt ~= "string" and rt ~= "table" then
        serialized_ret = tostring(ret_val)
    end

    return ok, serialized_ret, table.concat(logs_buf, "\n"), err_msg
end

-- =========================================================================
-- Per-Bot World Cache & World Scanner
-- =========================================================================

local _bot_world_cache = {}

local function _getBotCache(b_name)
    local key = tostring(b_name or "default")
    if not _bot_world_cache[key] then
        _bot_world_cache[key] = {
            last_world_name = "",
            last_tile_scan = 0,
            tiles_rle = "",
            players = {}
        }
    end
    return _bot_world_cache[key]
end

local function _isIterable(x)
    local t = type(x)
    return t == "table" or t == "userdata"
end

local function _iterList(list, fn)
    if not _isIterable(list) then return end
    local ok_len, n = pcall(function() return #list end)
    if ok_len and type(n) == "number" and n > 0 then
        for i = 1, n do
            local ok_i, item = pcall(function() return list[i] end)
            if ok_i and item ~= nil then
                fn(item, i)
            end
        end
        return
    end
    pcall(function()
        for k, v in pairs(list) do
            fn(v, k)
        end
    end)
end

local function scanLiveWorld(bot, b_name, world_name)
    local cache = _getBotCache(b_name)
    if not world_name or #world_name == 0 or world_name == "EXIT" then
        cache.tiles_rle = ""
        cache.players = {}
        cache.last_world_name = world_name or ""
        return "", {}
    end

    local now = os.time and os.time() or 0
    if world_name ~= cache.last_world_name or (now - cache.last_tile_scan) >= 5 or #cache.tiles_rle == 0 then
        cache.last_world_name = world_name
        cache.last_tile_scan = now

        local w = (bot.getWorld and bot:getWorld()) or (getWorld and getWorld())
        if w then
            local tiles = nil
            if w.getTiles then
                local ok, res = pcall(function() return w:getTiles() end)
                if ok and res then tiles = res end
            end
            if not tiles and w.getTilesSafe then
                local ok, res = pcall(function() return w:getTilesSafe() end)
                if ok and res then tiles = res end
            end
            if not tiles and getTiles then
                local ok, res = pcall(function() return getTiles() end)
                if ok and res then tiles = res end
            end

            if tiles and _isIterable(tiles) then
                local grid = {}
                local seq = 0
                local has_data = false
                _iterList(tiles, function(t)
                    seq = seq + 1
                    has_data = true
                    local fg = tonumber(safeCall(t, "fg", 0)) or 0
                    local tx = safeCall(t, "x", nil)
                    local ty = safeCall(t, "y", nil)
                    if type(tx) == "number" and type(ty) == "number" and tx >= 0 and tx < 100 and ty >= 0 and ty < 60 then
                        grid[(ty * 100) + tx + 1] = fg
                    elseif seq <= 6000 then
                        grid[seq] = fg
                    end
                end)

                if has_data then
                    local rle = {}
                    local curr_fg = nil
                    local count = 0
                    for i = 1, 6000 do
                        local fg = grid[i] or 0
                        if fg == curr_fg then
                            count = count + 1
                        else
                            if curr_fg ~= nil then
                                table.insert(rle, curr_fg .. ":" .. count)
                            end
                            curr_fg = fg
                            count = 1
                        end
                    end
                    if curr_fg ~= nil then
                        table.insert(rle, curr_fg .. ":" .. count)
                    end
                    cache.tiles_rle = table.concat(rle, ",")
                end
            end

            local players = {}
            local my_name = safeCall(bot, "name", "")
            local plist = nil
            if w.getPlayers then
                local ok, p = pcall(function() return w:getPlayers() end)
                if ok and p then plist = p end
            elseif getPlayers then
                local ok, p = pcall(function() return getPlayers() end)
                if ok and p then plist = p end
            end

            if plist and _isIterable(plist) then
                _iterList(plist, function(p)
                    local pname = safeCall(p, "name", "")
                    if pname ~= my_name and #pname > 0 then
                        local px = safeCall(p, "x", 0)
                        local py = safeCall(p, "y", 0)
                        if px > 100 then px = math.floor(px / 32) end
                        if py > 60 then py = math.floor(py / 32) end
                        table.insert(players, {
                            name = pname,
                            x = px,
                            y = py,
                            netid = safeCall(p, "netid", 0),
                            userid = safeCall(p, "userid", 0),
                            country = safeCall(p, "country", "")
                        })
                    end
                end)
                cache.players = players
            end
        end
    end
    return cache.tiles_rle, cache.players
end

local function _inspectLiveWorld(bot, filter_item_id)
    local w = (bot.getWorld and bot:getWorld()) or (getWorld and getWorld())
    if not w then
        return nil, "Bot is not currently inside any accessible world."
    end
    local w_name = safeCall(w, "name", "")
    if #w_name == 0 or w_name == "EXIT" then
        return { name = w_name, width = 0, height = 0, players = {}, objects = {}, tile_summary = {} }, nil
    end

    local width = tonumber(safeCall(w, "x", 100)) or 100
    local height = tonumber(safeCall(w, "y", 60)) or 60

    local players_out = {}
    local plist = nil
    pcall(function() plist = w.getPlayers and w:getPlayers() end)
    if plist and _isIterable(plist) then
        _iterList(plist, function(p)
            local px = safeCall(p, "x", 0)
            local py = safeCall(p, "y", 0)
            if px > 100 then px = math.floor(px / 32) end
            if py > 60 then py = math.floor(py / 32) end
            table.insert(players_out, {
                name = tostring(safeCall(p, "name", "")),
                netid = tonumber(safeCall(p, "netid", 0)) or 0,
                userid = tonumber(safeCall(p, "userid", 0)) or 0,
                x = px,
                y = py,
                country = tostring(safeCall(p, "country", "")),
                is_mod = safeCall(p, "is_mod", false) == true
            })
        end)
    end

    local objects_out = {}
    local olist = nil
    pcall(function() olist = w.getObjects and w:getObjects() end)
    if olist and _isIterable(olist) then
        _iterList(olist, function(o)
            if #objects_out >= 150 then return end
            local oid_item = tonumber(safeCall(o, "id", 0)) or 0
            if not filter_item_id or oid_item == tonumber(filter_item_id) then
                local ox = tonumber(safeCall(o, "x", 0)) or 0
                local oy = tonumber(safeCall(o, "y", 0)) or 0
                table.insert(objects_out, {
                    id = oid_item,
                    count = tonumber(safeCall(o, "count", 1)) or 1,
                    oid = tonumber(safeCall(o, "oid", 0)) or 0,
                    x = math.floor(ox / 32),
                    y = math.floor(oy / 32)
                })
            end
        end)
    end

    local fg_counts = {}
    local tiles = nil
    pcall(function() tiles = (w.getTiles and w:getTiles()) or (w.getTilesSafe and w:getTilesSafe()) end)
    if tiles and _isIterable(tiles) then
        _iterList(tiles, function(t)
            local fg = tonumber(safeCall(t, "fg", 0)) or 0
            if fg > 0 then
                fg_counts[fg] = (fg_counts[fg] or 0) + 1
            end
        end)
    end

    local summary_list = {}
    for iid, cnt in pairs(fg_counts) do
        table.insert(summary_list, { id = iid, count = cnt })
    end
    table.sort(summary_list, function(a, b) return a.count > b.count end)
    while #summary_list > 40 do
        table.remove(summary_list)
    end

    return {
        name = w_name,
        width = width,
        height = height,
        bot_x = tonumber(safeCall(bot, "x", 0)) or 0,
        bot_y = tonumber(safeCall(bot, "y", 0)) or 0,
        players = players_out,
        objects = objects_out,
        tile_summary = summary_list
    }, nil
end

local function _inspectTile(bot, tx, ty)
    local w = (bot.getWorld and bot:getWorld()) or (getWorld and getWorld())
    if not w then
        return nil, "Bot is not in a world"
    end
    local ok, tile = pcall(function() return w:getTile(tx, ty) end)
    if not ok or not tile then
        return nil, "Could not read tile at (" .. tostring(tx) .. "," .. tostring(ty) .. ")"
    end

    local info = {
        x = tx,
        y = ty,
        fg = tonumber(safeCall(tile, "fg", 0)) or 0,
        bg = tonumber(safeCall(tile, "bg", 0)) or 0,
        flags = tonumber(safeCall(tile, "flags", 0)) or 0,
        ready = safeCall(tile, "canHarvest", nil),
        has_extra = safeCall(tile, "hasExtra", false) == true
    }

    if tile.getExtra then
        local ok_ex, ex = pcall(function() return tile:getExtra() end)
        if ok_ex and ex then
            info.extra = {
                label = safeCall(ex, "label", nil),
                id = safeCall(ex, "id", nil),
                item_id = safeCall(ex, "item_id", nil),
                count = safeCall(ex, "count", nil),
                price = safeCall(ex, "price", nil),
                owner = safeCall(ex, "owner", nil),
                enabled = safeCall(ex, "enabled", nil),
                volume = safeCall(ex, "volume", nil)
            }
        end
    end
    return info, nil
end

local function _countWorldItem(bot, item_id)
    local w = (bot.getWorld and bot:getWorld()) or (getWorld and getWorld())
    if not w then
        return nil, "Bot is not in a world"
    end
    local iid = tonumber(item_id) or 0
    local tile_fg = 0
    local tile_bg = 0
    local ready_trees = 0
    local dropped_stacks = 0
    local dropped_total = 0
    local coords = {}

    local tiles = nil
    pcall(function() tiles = (w.getTiles and w:getTiles()) or (w.getTilesSafe and w:getTilesSafe()) end)
    if tiles and _isIterable(tiles) then
        _iterList(tiles, function(t)
            local fg = tonumber(safeCall(t, "fg", 0)) or 0
            local bg = tonumber(safeCall(t, "bg", 0)) or 0
            local tx = tonumber(safeCall(t, "x", 0)) or 0
            local ty = tonumber(safeCall(t, "y", 0)) or 0
            if fg == iid then
                tile_fg = tile_fg + 1
                if safeCall(t, "canHarvest", false) == true then
                    ready_trees = ready_trees + 1
                end
                if #coords < 40 then
                    table.insert(coords, { kind = "tile_fg", x = tx, y = ty })
                end
            end
            if bg == iid then
                tile_bg = tile_bg + 1
            end
        end)
    end

    local objs = nil
    pcall(function() objs = w.getObjects and w:getObjects() end)
    if objs and _isIterable(objs) then
        _iterList(objs, function(o)
            if tonumber(safeCall(o, "id", 0)) == iid then
                local cnt = tonumber(safeCall(o, "count", 1)) or 1
                dropped_stacks = dropped_stacks + 1
                dropped_total = dropped_total + cnt
                if #coords < 40 then
                    local ox = math.floor((tonumber(safeCall(o, "x", 0)) or 0) / 32)
                    local oy = math.floor((tonumber(safeCall(o, "y", 0)) or 0) / 32)
                    table.insert(coords, { kind = "dropped", x = ox, y = oy, count = cnt })
                end
            end
        end)
    end

    return {
        world = tostring(safeCall(w, "name", "")),
        item_id = iid,
        tile_fg_count = tile_fg,
        tile_bg_count = tile_bg,
        ready_trees = ready_trees,
        dropped_stacks = dropped_stacks,
        dropped_total = dropped_total,
        sample_coords = coords
    }, nil
end

local function _readBotLogs(bot)
    local log_txt = ""
    local console_txt = ""
    if bot.getLog then
        local ok, l_obj = pcall(function() return bot:getLog() end)
        if ok and l_obj then
            local c = safeCall(l_obj, "content", "")
            if c then log_txt = tostring(c) end
        end
    end
    if bot.getConsole then
        local ok, c_obj = pcall(function() return bot:getConsole() end)
        if ok and c_obj then
            local c = safeCall(c_obj, "contents", "")
            if c then console_txt = tostring(c) end
        end
    end
    return log_txt, console_txt
end

local function buildBotPayload(bot)
    local inv_table = {}
    local inv = bot.getInventory and bot:getInventory()
    if inv then
        local items = inv.getItems and inv:getItems()
        if items and _isIterable(items) then
            _iterList(items, function(item)
                table.insert(inv_table, {
                    id = item.id or 0,
                    count = item.count or 0,
                    isActive = item.isActive or false
                })
            end)
        end
    end

    local ping = safeCall(bot, "getPing", nil)
    if ping == nil or tonumber(ping) == nil then
        ping = safeCall(bot, "ping", 0)
    end
    ping = tonumber(ping) or 0

    local b_name = tostring(safeCall(bot, "name", "LuciferBot"))
    local b_status = safeCall(bot, "status", 0)
    local b_x = safeCall(bot, "x", 0)
    local b_y = safeCall(bot, "y", 0)

    local b_gems = safeCall(bot, "gem_count", nil)
    if b_gems == nil or tonumber(b_gems) == nil or tonumber(b_gems) == 0 then
        local b_obtained = safeCall(bot, "obtained_gem_count", nil)
        if b_obtained ~= nil and tonumber(b_obtained) and tonumber(b_obtained) > 0 then
            b_gems = b_obtained
        elseif b_gems == nil then
            b_gems = safeCall(bot, "gems", 0)
        end
    end
    b_gems = tonumber(b_gems) or 0
    local b_pearls = safeCall(bot, "pearl_count", 0)
    local b_vouchers = safeCall(bot, "voucher_count", 0)
    local b_level = safeCall(bot, "level", 1)
    local g_status = safeCall(bot, "google_status", 0)
    local cap_status = safeCall(bot, "captcha_status", 0)

    local world_name = ""
    local world_public = true
    local w = bot.getWorld and bot:getWorld()
    if w then
        world_name = safeCall(w, "name", "")
        local pub = safeCall(w, "public", true)
        if pub == false then
            world_public = false
        end
    else
        world_name = bot.world or ""
    end

    local auto_tbl = {}
    if bot.auto_farm then auto_tbl.auto_farm = safeCall(bot.auto_farm, "enabled", false) end
    if bot.auto_geiger then auto_tbl.auto_geiger = safeCall(bot.auto_geiger, "enabled", false) end
    if bot.auto_spam then auto_tbl.auto_spam = safeCall(bot.auto_spam, "enabled", false) end
    if bot.auto_fish then auto_tbl.auto_fish = safeCall(bot.auto_fish, "enabled", false) end
    if bot.rotation then auto_tbl.rotation = safeCall(bot.rotation, "enabled", false) end
    if bot.auto_cook then auto_tbl.auto_cook = safeCall(bot.auto_cook, "enabled", false) end
    if bot.auto_transfer then auto_tbl.auto_transfer = safeCall(bot.auto_transfer, "enabled", false) end
    if bot.auto_harvest then auto_tbl.auto_harvest = safeCall(bot.auto_harvest, "enabled", false) end
    if bot.auto_plant then auto_tbl.auto_plant = safeCall(bot.auto_plant, "enabled", false) end
    auto_tbl.auto_collect = bot.auto_collect or false
    auto_tbl.auto_trash = bot.auto_trash or false
    auto_tbl.auto_reconnect = safeCall(bot, "auto_reconnect", false) == true
    auto_tbl.legit_mode = safeCall(bot, "legit_mode", false) == true
    auto_tbl.anti_fire = safeCall(bot, "anti_fire", false) == true
    auto_tbl.anti_toxic = safeCall(bot, "anti_toxic", false) == true

    local log_txt, console_txt = _readBotLogs(bot)
    local recent_logs = (#log_txt > 0 and log_txt) or console_txt
    if #recent_logs > 2500 then
        recent_logs = recent_logs:sub(#recent_logs - 2500)
    end

    local tiles_rle, other_players = scanLiveWorld(bot, b_name, world_name)

    local results_batch = {}
    if #_pending_results > 0 then
        results_batch = _pending_results
        _pending_results = {}
    end

    return {
        name = b_name,
        bot_name = b_name,
        owner_token = OWNER_TOKEN,
        status = getStatusName(b_status),
        raw_status = tonumber(b_status) or 0,
        google_status = tonumber(g_status) or 0,
        captcha_status = getCaptchaName(cap_status),
        world = tostring(world_name),
        world_public = world_public,
        x = tonumber(b_x) or 0,
        y = tonumber(b_y) or 0,
        gem_count = tonumber(b_gems) or 0,
        gems = tonumber(b_gems) or 0,
        pearl_count = tonumber(b_pearls) or 0,
        voucher_count = tonumber(b_vouchers) or 0,
        level = tonumber(b_level) or 1,
        ping = tonumber(ping) or 0,
        inventory = inv_table,
        automations = auto_tbl,
        logs = recent_logs,
        tiles_rle = tostring(tiles_rle or ""),
        players = other_players or {},
        captcha_url = (bot.getCaptcha and bot:getCaptcha()) or "",
        command_results = results_batch
    }
end

-- =========================================================================
-- Command Dispatcher (Human-Equivalent Lucifer API Coverage)
-- =========================================================================

local function _applySettingsTable(target_obj, settings_tbl)
    local applied = {}
    local failed = {}
    if not target_obj or type(settings_tbl) ~= "table" then
        return applied, failed
    end
    for k, v in pairs(settings_tbl) do
        local ok = pcall(function()
            target_obj[k] = v
        end)
        if ok then
            table.insert(applied, tostring(k))
        else
            table.insert(failed, tostring(k))
        end
    end
    return applied, failed
end

local function executeCommand(bot, cmd)
    if not cmd or not cmd.action then return end
    local action = tostring(cmd.action)
    local params = cmd.params or {}
    local cmd_id = cmd.cmd_id or cmd.id or ""
    local b_name = tostring(safeCall(bot, "name", "LuciferBot"))

    local res_ok = true
    local res_val = nil
    local res_out = ""
    local res_err = nil

    if action == "warp" then
        if params.id and #tostring(params.id) > 0 then
            res_ok, res_err = pcall(function() bot:warp(tostring(params.world), tostring(params.id)) end)
        else
            res_ok, res_err = pcall(function() bot:warp(tostring(params.world)) end)
        end

    elseif action == "say" then
        res_ok, res_err = pcall(function() bot:say(tostring(params.text or "")) end)

    elseif action == "find_path" then
        res_ok, res_err = pcall(function() bot:findPath(tonumber(params.x) or 0, tonumber(params.y) or 0) end)

    elseif action == "find_world_path" then
        local ok_call, r = pcall(function() return bot:findWorldPath(tonumber(params.x) or 0, tonumber(params.y) or 0) end)
        res_ok = ok_call
        if ok_call then res_val = r else res_err = tostring(r) end

    elseif action == "move" then
        local mode = tostring(params.mode or params.direction or "")
        local rng = tonumber(params.range or params.steps or 1) or 1
        res_ok, res_err = pcall(function()
            if mode == "left" then
                bot:moveLeft(rng)
            elseif mode == "right" then
                bot:moveRight(rng)
            elseif mode == "up" then
                bot:moveUp(rng)
            elseif mode == "down" then
                bot:moveDown(rng)
            elseif mode == "tile" and params.x ~= nil and params.y ~= nil then
                bot:moveTile(tonumber(params.x), tonumber(params.y))
            elseif params.dx ~= nil or params.dy ~= nil then
                bot:moveTo(tonumber(params.dx) or 0, tonumber(params.dy) or 0)
            elseif params.x ~= nil and params.y ~= nil then
                bot:moveTile(tonumber(params.x), tonumber(params.y))
            end
            if params.face_left ~= nil and bot.setDirection then
                bot:setDirection(params.face_left == true)
            end
        end)

    elseif action == "place" then
        res_ok, res_err = pcall(function()
            bot:place(tonumber(params.x) or 0, tonumber(params.y) or 0, tonumber(params.item_id) or 0)
        end)

    elseif action == "hit" then
        res_ok, res_err = pcall(function()
            bot:hit(tonumber(params.x) or 0, tonumber(params.y) or 0)
        end)

    elseif action == "wrench" then
        res_ok, res_err = pcall(function()
            if params.netid ~= nil and bot.wrenchPlayer then
                bot:wrenchPlayer(tonumber(params.netid))
            else
                bot:wrench(tonumber(params.x) or 0, tonumber(params.y) or 0)
            end
        end)

    elseif action == "activate" or action == "active" then
        res_ok, res_err = pcall(function()
            local tx = tonumber(params.x) or 0
            local ty = tonumber(params.y) or 0
            if bot.active then
                bot:active(tx, ty)
            elseif bot.activate then
                bot:activate(tx, ty)
            end
        end)

    elseif action == "enter_door" or action == "enter" then
        res_ok, res_err = pcall(function()
            if params.password and #tostring(params.password) > 0 then
                bot:enter(tostring(params.password))
            else
                bot:enter()
            end
        end)

    elseif action == "collect" then
        local range = tonumber(params.range) or 2
        local interval = tonumber(params.interval) or 150
        res_ok, res_err = pcall(function()
            if params.item_id and bot.collectByID then
                bot:collectByID(tonumber(params.item_id))
            elseif params.oid and bot.collectObject then
                bot:collectObject(tonumber(params.oid), range)
            else
                bot:collect(range, interval)
            end
        end)

    elseif action == "drop" then
        local iid = tonumber(params.item_id) or 0
        local count = tonumber(params.count) or 1
        res_ok, res_err = pcall(function()
            if params.fast and bot.fastDrop then
                bot:fastDrop(iid, count)
            else
                bot:drop(iid, count)
            end
        end)

    elseif action == "trash" then
        local iid = tonumber(params.item_id) or 0
        local count = tonumber(params.count) or 1
        res_ok, res_err = pcall(function()
            if params.fast and bot.fastTrash then
                bot:fastTrash(iid, count)
            else
                bot:trash(iid, count)
            end
        end)

    elseif action == "wear" then
        res_ok, res_err = pcall(function() bot:wear(tonumber(params.item_id) or 0) end)

    elseif action == "unwear" then
        res_ok, res_err = pcall(function() bot:unwear(tonumber(params.item_id) or 0) end)

    elseif action == "use" then
        res_ok, res_err = pcall(function() bot:use(tonumber(params.item_id) or 0) end)

    elseif action == "buy" then
        res_ok, res_err = pcall(function() bot:buy(tostring(params.pack or params.item or "")) end)

    elseif action == "retrieve" then
        res_ok, res_err = pcall(function()
            local tx = tonumber(params.x) or 0
            local ty = tonumber(params.y) or 0
            if params.count then
                bot:retrieve(tx, ty, tonumber(params.count))
            else
                bot:retrieve(tx, ty)
            end
        end)

    elseif action == "send_packet" then
        res_ok, res_err = pcall(function()
            bot:sendPacket(tonumber(params.packet_type or params.type or 2), tostring(params.text or params.packet or ""))
        end)

    elseif action == "send_raw" then
        res_ok, res_err = pcall(function()
            if GameUpdatePacket and GameUpdatePacket.new then
                local pkt = GameUpdatePacket.new()
                if params.type ~= nil then pkt.type = tonumber(params.type) end
                if params.int_data ~= nil then pkt.int_data = tonumber(params.int_data) end
                if params.int_x ~= nil then pkt.int_x = tonumber(params.int_x) end
                if params.int_y ~= nil then pkt.int_y = tonumber(params.int_y) end
                if params.pos_x ~= nil then pkt.pos_x = tonumber(params.pos_x) end
                if params.pos_y ~= nil then pkt.pos_y = tonumber(params.pos_y) end
                if params.vec_x ~= nil then pkt.vec_x = tonumber(params.vec_x) end
                if params.vec_y ~= nil then pkt.vec_y = tonumber(params.vec_y) end
                if params.flags ~= nil then pkt.flags = tonumber(params.flags) end
                bot:sendRaw(pkt)
            else
                error("GameUpdatePacket is not available in this Lucifer build")
            end
        end)

    elseif action == "leave" then
        res_ok, res_err = pcall(function() bot:leaveWorld() end)

    elseif action == "respawn" then
        res_ok, res_err = pcall(function() bot:respawn() end)

    elseif action == "connect" then
        res_ok, res_err = pcall(function() bot:connect() end)

    elseif action == "disconnect" then
        res_ok, res_err = pcall(function() bot:disconnect() end)

    elseif action == "stop_script" then
        res_ok, res_err = pcall(function()
            if bot.stopScript then
                bot:stopScript()
            end
        end)

    elseif action == "run_script" or action == "eval_sync" then
        local code_str = tostring(params.code or "")
        if #code_str > 0 then
            if params.use_thread and runThread then
                local chunk, cerr = load(code_str)
                if chunk then
                    res_ok, res_err = pcall(function() runThread(chunk) end)
                    res_out = "[LuciferBridge] Started background thread via runThread"
                else
                    res_ok = false
                    res_err = "Syntax error: " .. tostring(cerr)
                end
            elseif params.use_bot_runner and bot.runScript then
                res_ok, res_err = pcall(function() bot:runScript(code_str) end)
                res_out = "[LuciferBridge] Dispatched to bot:runScript"
            else
                res_ok, res_val, res_out, res_err = _execLuaWithCapture(code_str, bot)
            end
        else
            res_ok = false
            res_err = "Empty Lua code payload"
        end

    elseif action == "inspect_world" then
        local data, err = _inspectLiveWorld(bot, params.filter_item_id)
        if data then
            res_ok = true
            res_val = data
        else
            res_ok = false
            res_err = err
        end

    elseif action == "inspect_tile" then
        local data, err = _inspectTile(bot, tonumber(params.x) or 0, tonumber(params.y) or 0)
        if data then
            res_ok = true
            res_val = data
        else
            res_ok = false
            res_err = err
        end

    elseif action == "world_count_item" then
        local data, err = _countWorldItem(bot, params.item_id)
        if data then
            res_ok = true
            res_val = data
        else
            res_ok = false
            res_err = err
        end

    elseif action == "get_console_logs" then
        local log_txt, con_txt = _readBotLogs(bot)
        if params.clear then
            pcall(function() if bot.clearConsole then bot:clearConsole() end end)
            pcall(function() if clearConsole then clearConsole() end end)
        end
        res_ok = true
        res_val = { bot_log = log_txt, console = con_txt }

    elseif action == "add_bot" then
        res_ok, res_err = pcall(function()
            local lt = tostring(params.login_type or "growid")
            local nm = tostring(params.name or "")
            local pw = tostring(params.password or "")
            local rec = tostring(params.recovery or "")
            if lt == "ubi" and addUbiBot then
                addUbiBot(nm, pw, rec)
            elseif lt == "steam" and addSteamBot then
                addSteamBot(nm, pw)
            elseif lt == "token" and addTokenBot then
                addTokenBot(nm, pw)
            elseif addBot then
                if #rec > 0 then
                    addBot(nm, pw, rec)
                elseif #pw > 0 then
                    addBot(nm, pw)
                else
                    addBot(nm)
                end
            else
                error("addBot API unavailable")
            end
        end)

    elseif action == "remove_bot" then
        res_ok, res_err = pcall(function()
            if removeBot then
                removeBot(tostring(params.target_bot or params.name or b_name))
            else
                error("removeBot API unavailable")
            end
        end)

    elseif action == "update_identity" then
        res_ok, res_err = pcall(function()
            if params.country and bot.setCountry then bot:setCountry(tostring(params.country)) end
            if params.mac and bot.setMac then bot:setMac(tostring(params.mac)) end
            if params.rid and bot.setRid then bot:setRid(tostring(params.rid)) end
            if params.skin and bot.setSkin then bot:setSkin(tonumber(params.skin) or 0) end
            if params.platform and bot.setPlatform then
                local pval = (Platform and Platform[params.platform]) or params.platform
                bot:setPlatform(pval)
            end
            if params.bubble and bot.setBubble then
                local bval = (Bubble and Bubble[params.bubble]) or params.bubble
                bot:setBubble(bval)
            end
        end)

    elseif action == "set_proxy" then
        local ip = tostring(params.ip or "")
        local port = tonumber(params.port) or 0
        local user = tostring(params.username or params.user or "")
        local pass = tostring(params.password or params.pass or "")
        if ip ~= "" and port > 0 then
            local updated = false
            if bot.updateProxy then
                local ok = pcall(function() bot:updateProxy(ip, port, user, pass) end)
                if ok then updated = true end
            end
            if not updated and bot.setProxy then
                local ok = pcall(function() bot:setProxy(ip, port, user, pass) end)
                if ok then updated = true end
            end
            if not updated and Proxy and Proxy.new then
                local ok, p = pcall(function() return Proxy.new(ip, port, user, pass) end)
                if ok and p then
                    bot.proxy = p
                    updated = true
                end
            end
            if not updated and Socks5Proxy and Socks5Proxy.new then
                local ok, p = pcall(function() return Socks5Proxy.new(ip, port, user, pass) end)
                if ok and p then
                    bot.proxy = p
                    updated = true
                end
            end
            res_ok = updated
            if not updated then res_err = "Failed to bind proxy to bot" end
        else
            res_ok = false
            res_err = "Invalid proxy ip or port"
        end

    elseif action == "switch_proxy" then
        res_ok, res_err = pcall(function()
            local pm = getProxyManager and getProxyManager()
            if pm and pm.switchProxy then
                pm:switchProxy(bot)
            elseif bot.switchProxy then
                bot:switchProxy()
            elseif bot.nextProxy then
                bot:nextProxy()
            else
                error("No switchProxy API found on ProxyManager or bot")
            end
        end)

    elseif action == "proxy_manager" then
        local pm = getProxyManager and getProxyManager()
        if not pm then
            res_ok = false
            res_err = "getProxyManager() unavailable"
        else
            local sub = tostring(params.op or "")
            res_ok, res_err = pcall(function()
                if sub == "add" then
                    if addProxy then addProxy(tostring(params.proxy_str or "")) else pm:addProxy(tostring(params.proxy_str or "")) end
                elseif sub == "remove" then
                    if removeProxy then removeProxy(tostring(params.ip or ""), tonumber(params.port) or 0) else pm:removeProxy(tostring(params.ip or ""), tonumber(params.port) or 0) end
                elseif sub == "set_limit" and pm.setLimit then
                    pm:setLimit(tonumber(params.limit) or 1)
                elseif type(params.settings) == "table" then
                    _applySettingsTable(pm, params.settings)
                end
            end)
        end

    elseif action == "world_manager" then
        local wm = (getWorldManager and getWorldManager()) or (bot.rotation and bot.rotation.world_manager)
        if not wm then
            res_ok = false
            res_err = "WorldManager unavailable"
        else
            local op = tostring(params.op or "")
            local st_type = (StorageType and StorageType[tostring(params.storage_type or "seed")]) or params.storage_type
            res_ok, res_err = pcall(function()
                if op == "add_farm" and wm.addFarm then
                    wm:addFarm(tostring(params.world or ""), tonumber(params.item_id) or 0)
                elseif op == "remove_farm" and wm.removeFarm then
                    wm:removeFarm(tostring(params.world or ""))
                elseif op == "add_storage" and wm.addStorage then
                    wm:addStorage(tostring(params.world or ""), st_type, tonumber(params.item_id) or 0)
                elseif op == "remove_storage" and wm.removeStorage then
                    wm:removeStorage(tostring(params.world or ""), st_type)
                elseif op == "select_all" and wm.selectAll then
                    wm:selectAll()
                elseif op == "unselect_all" and wm.unselectAll then
                    wm:unselectAll()
                elseif op == "select_farm" and wm.selectFarm then
                    wm:selectFarm(tostring(params.world or ""))
                elseif op == "unselect_farm" and wm.unselectFarm then
                    wm:unselectFarm(tostring(params.world or ""))
                end
            end)
        end

    elseif action == "configure_subsystem" then
        local sub_name = tostring(params.subsystem or "")
        local target_obj = (sub_name == "bot" and bot) or safeCall(bot, sub_name, nil)
        if not target_obj then
            res_ok = false
            res_err = "Subsystem not found on bot: " .. sub_name
        else
            if params.enabled ~= nil then
                safeSet(target_obj, "enabled", params.enabled == true)
            end
            local applied, failed = _applySettingsTable(target_obj, params.settings or {})
            res_ok = true
            res_val = { subsystem = sub_name, applied = applied, failed = failed }
        end

    elseif action == "set_automation" then
        local auto_name = tostring(params.automation or "")
        local enabled = params.enabled == true
        local target = safeCall(bot, auto_name, nil)
        if type(target) == "userdata" or type(target) == "table" then
            safeSet(target, "enabled", enabled)
        else
            safeSet(bot, auto_name, enabled)
        end

    elseif action == "set_setting" then
        local key = tostring(params.key or params.setting or "")
        local val = params.value
        if key ~= "" then
            if bot[key] ~= nil or type(bot[key]) == "boolean" or type(bot[key]) == "number" then
                safeSet(bot, key, val)
            elseif bot.auto_farm and bot.auto_farm[key] ~= nil then
                safeSet(bot.auto_farm, key, val)
            elseif bot.rotation and bot.rotation[key] ~= nil then
                safeSet(bot.rotation, key, val)
            elseif bot.auto_spam and bot.auto_spam[key] ~= nil then
                safeSet(bot.auto_spam, key, val)
            elseif bot.auto_geiger and bot.auto_geiger[key] ~= nil then
                safeSet(bot.auto_geiger, key, val)
            else
                safeSet(bot, key, val)
            end
        end

    elseif action == "trash_pack_manager" then
        local op = tostring(params.op or "")
        res_ok, res_err = pcall(function()
            if op == "set_trash_list" and setTrashList and type(params.items) == "table" then
                setTrashList(params.items)
            elseif op == "get_trash_list" and getTrashList then
                res_val = getTrashList()
            elseif op == "add_pack" and addPack then
                addPack(tostring(params.pack_name or ""), tonumber(params.item_id) or 0)
            elseif op == "remove_pack" and removePack then
                removePack(tostring(params.pack_name or ""))
            end
        end)

    elseif action == "file_ops" then
        local op = tostring(params.op or "read")
        local fpath = tostring(params.path or "")
        res_ok, res_err = pcall(function()
            if op == "read" and read then
                res_val = read(fpath)
            elseif op == "write" and write then
                write(fpath, tostring(params.content or ""))
            elseif op == "append" and append then
                append(fpath, tostring(params.content or ""))
            else
                error("Unsupported file_ops operation or missing file API")
            end
        end)

    elseif action == "refresh_map" or action == "get_map" then
        local cache = _getBotCache(b_name)
        cache.last_tile_scan = 0
        res_out = "[LuciferBridge] Immediate world map scan triggered"

    else
        res_ok = false
        res_err = "Unknown bridge action: " .. action
    end

    if cmd_id and #tostring(cmd_id) > 0 then
        _recordResult({
            cmd_id = tostring(cmd_id),
            bot = b_name,
            ok = res_ok == true,
            result = res_val,
            output = tostring(res_out or ""),
            error = res_err and tostring(res_err) or nil
        })
    end
end

-- =========================================================================
-- Main Polling Loop
-- =========================================================================

function runBridge()
    print("==========================================================")
    print("  LUCIFER MULTIBOT MCP & DISCORD BRIDGE STARTED (v2.5)")
    print("  Target Relay: " .. SERVER_URL)
    if #OWNER_TOKEN > 0 then
        print("  Tenant Mode: MULTI-TENANT TOKEN ACTIVE")
    else
        print("  Tenant Mode: LOCAL")
    end
    print("==========================================================")

    while true do
        local bots = {}
        if getBots then
            local ok, list = pcall(getBots)
            if ok and list then
                if type(list) == "table" then
                    for _, b in pairs(list) do
                        if b then table.insert(bots, b) end
                    end
                elseif type(list) == "userdata" then
                    pcall(function()
                        for _, b in ipairs(list) do
                            if b then table.insert(bots, b) end
                        end
                    end)
                    if #bots == 0 and list.size then
                        pcall(function()
                            local sz = (type(list.size) == "function" and list:size()) or list.size or 0
                            for i = 0, sz - 1 do
                                local b = list:at(i) or list[i] or list[i + 1]
                                if b then table.insert(bots, b) end
                            end
                        end)
                    end
                end
            end
        end
        if #bots == 0 and getBot then
            local ok, b = pcall(getBot)
            if ok and b then
                table.insert(bots, b)
            end
        end
        if #bots == 0 and bot then
            table.insert(bots, bot)
        end

        if #bots == 0 then
            print("[LuciferBridge] Waiting for bot instance in Lucifer... (Check Bots tab)")
        end

        for _, b_inst in ipairs(bots) do
            local payload = buildBotPayload(b_inst)
            local ok, response = httpPostJson("/api/heartbeat", payload)

            if ok and response then
                local body_str = nil
                if type(response.body) == "string" then
                    body_str = response.body
                elseif type(response.body) == "function" then
                    pcall(function() body_str = response:body() end)
                end

                print(string.format("[LuciferBridge] Heartbeat OK: '%s' | Status: %s (%s) | World: %s | Gems: %d | Ping: %d ms | Relay: %s",
                    tostring(payload.name), tostring(payload.status), tostring(payload.raw_status), tostring(payload.world), tonumber(payload.gem_count) or 0, tonumber(payload.ping) or 0, tostring(response.status or 200)))

                if body_str then
                    local res_data = JSON.decode(body_str)
                    if res_data and res_data.commands then
                        for _, cmd in ipairs(res_data.commands) do
                            executeCommand(b_inst, cmd)
                        end
                    end
                end
            else
                print(string.format("[LuciferBridge] Heartbeat HTTP error for '%s': %s", tostring(payload.name), tostring(response)))
            end

            if #bots > 1 then
                sleep(25)
            end
        end

        sleep(HEARTBEAT_INTERVAL_MS)
    end
end

runBridge()
