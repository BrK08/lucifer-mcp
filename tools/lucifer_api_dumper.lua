--[[
  LUCIFER MULTIBOT — 100% OFFLINE API DEEP DUMPER v2.0
  Created for BrK08/lucifer-mcp (mr_berk)

  ÖZELLİKLER:
  - Oyuna girmeye, dünyada olmaya veya sunucuya bağlanmaya GEREK YOKTUR.
  - "HTTP Block" hatası alsanız bile Lucifer ana menüsündeyken çalışır!
  - Tüm global fonksiyonları, tabloları, C++ metatable'larını, enumları,
    Bot, AutoFarm, AutoGeiger, AutoSpam, WorldManager, ProxyManager ve
    HttpClient metotlarını tarar.
  - Çıktıyı 2 farklı formatta kaydeder:
      1) "lucifer_dumped_api.txt"  -> Tertemiz, okunabilir metin formatı
      2) "lucifer_dumped_api.json" -> Yapay zeka ve sistemler için tam JSON
  - Eger Python Relay açıksa (127.0.0.1:8829/api/dump) veriyi otomatik iletir.
--]]

local RELAY_URL = "http://127.0.0.1:8829"

local dump = {
    metadata = {
        title = "Lucifer Multibot Deep API Dump",
        version = "v2.0",
        timestamp = os.time and os.time() or 0
    },
    globals = {},
    enums = {},
    bot_members = {},
    automations = {},
    world_manager_members = {},
    proxy_manager_members = {},
    http_client_members = {},
    variant_list_members = {},
    classes_found = {}
}

-- =========================================================================
-- Metatable ve Üye İnceleyici
-- =========================================================================
local function inspectMembers(obj, target_table)
    if not obj then return end

    -- 1. Doğrudan alanlar
    pcall(function()
        for k, v in pairs(obj) do
            local val_type = type(v)
            if val_type == "function" then
                target_table[tostring(k)] = "method"
            elseif val_type == "table" or val_type == "userdata" then
                target_table[tostring(k)] = "sub_object (" .. val_type .. ")"
            else
                target_table[tostring(k)] = "property (" .. val_type .. ")"
            end
        end
    end)

    -- 2. Metatable alanları (C++ bindingleri çoğunlukla buradadır)
    local mt = nil
    if debug and debug.getmetatable then
        pcall(function() mt = debug.getmetatable(obj) end)
    end
    if not mt and getmetatable then
        pcall(function() mt = getmetatable(obj) end)
    end

    if mt and type(mt) == "table" then
        if type(mt.__index) == "table" then
            for k, v in pairs(mt.__index) do
                local val_type = type(v)
                target_table[tostring(k)] = (val_type == "function") and "method" or ("property (" .. val_type .. ")")
            end
        end
        for k, v in pairs(mt) do
            local key_str = tostring(k)
            if key_str:sub(1, 2) ~= "__" then
                local val_type = type(v)
                target_table[key_str] = (val_type == "function") and "method" or ("property (" .. val_type .. ")")
            end
        end
    end
end

print("==========================================================")
print("  😈 LUCIFER %100 OFFLINE API TARAYICI v2.0")
print("  (Oyuna girmeden tum Lucifer fonksiyonlarini deşifre eder)")
print("==========================================================")

-- 1. _G (Global) Taraması
for k, v in pairs(_G) do
    local key_str = tostring(k)
    local t = type(v)
    if t == "function" then
        dump.globals[key_str] = "function"
    elseif t == "table" or t == "userdata" then
        -- Enum kontrolü
        local is_enum = false
        local enum_values = {}
        pcall(function()
            local count = 0
            for ek, ev in pairs(v) do
                count = count + 1
                enum_values[tostring(ek)] = tostring(ev)
            end
            if count > 0 and count < 150 then
                dump.enums[key_str] = enum_values
                is_enum = true
            end
        end)
        if not is_enum then
            dump.globals[key_str] = t
            -- Potansiyel sınıf mı? (World, Tile, Player vb.)
            pcall(function()
                local sub = {}
                inspectMembers(v, sub)
                if next(sub) then
                    dump.classes_found[key_str] = sub
                end
            end)
        end
    else
        dump.globals[key_str] = t
    end
end

-- 2. Bot Nesnesi Taraması (Offline Dummy Ekleme Garantisi)
local bot = nil
if getBot then
    pcall(function() bot = getBot() end)
end

if not bot and getBots then
    pcall(function()
        local bots = getBots()
        if type(bots) == "table" then
            for _, b in pairs(bots) do bot = b break end
        end
    end)
end

-- Eğer menüde hiç bot yoksa bile geçici dummy bot oluşturup metotlarını döküyoruz!
if not bot and addBot then
    pcall(function()
        bot = addBot("__ApiDumperDummy", "dummy_pass_123")
        print("[LuciferDumper] Metotlari okumak icin gecici dummy bot uretildi.")
    end)
end

if bot then
    print("[LuciferDumper] Bot nesnesi bulundu, metatable ve uyeler inceleniyor...")
    inspectMembers(bot, dump.bot_members)

    -- Alt otomasyon motorlarını tara
    local autos = {
        "auto_farm", "auto_geiger", "auto_spam", "auto_fish",
        "auto_message", "auto_cook", "auto_carnival", "auto_parkour",
        "auto_crime", "rotation", "console", "log", "login"
    }
    for _, auto_name in ipairs(autos) do
        pcall(function()
            local inst = bot[auto_name]
            if inst then
                dump.automations[auto_name] = {}
                inspectMembers(inst, dump.automations[auto_name])
            end
        end)
    end

    -- Alt getter metotlarının döndürdüğü nesneler
    local getters = {
        { name = "inventory", fn = bot.getInventory },
        { name = "console", fn = bot.getConsole },
        { name = "log", fn = bot.getLog },
        { name = "login", fn = bot.getLogin },
        { name = "proxy", fn = bot.getProxy }
    }
    for _, g in ipairs(getters) do
        if g.fn then
            pcall(function()
                local obj = g.fn(bot)
                if obj then
                    dump.automations[g.name] = {}
                    inspectMembers(obj, dump.automations[g.name])
                end
            end)
        end
    end

    -- Dummy botu temizle (opsiyonel)
    if bot.name == "__ApiDumperDummy" and removeBot then
        pcall(function() removeBot("__ApiDumperDummy") end)
    end
else
    print("⚠️ [LuciferDumper] Bot nesnesi alinamadi (Menuden bir bot secin veya addBot kullanin).")
end

-- 3. Proxy Manager Taraması
if getProxyManager then
    pcall(function()
        local pm = getProxyManager()
        if pm then inspectMembers(pm, dump.proxy_manager_members) end
    end)
end

-- 4. World Manager Taraması
if getWorldManager then
    pcall(function()
        local wm = getWorldManager()
        if wm then inspectMembers(wm, dump.world_manager_members) end
    end)
end

-- 5. HttpClient Taraması
if HttpClient and HttpClient.new then
    pcall(function()
        local hc = HttpClient.new()
        if hc then inspectMembers(hc, dump.http_client_members) end
    end)
end

-- 6. Variantlist Taraması
if variantlist and variantlist.new then
    pcall(function()
        local vl = variantlist.new()
        if vl then inspectMembers(vl, dump.variant_list_members) end
    end)
end

-- =========================================================================
-- Okunabilir Metin Formatı (TXT Raporu)
-- =========================================================================
local lines = {}
table.insert(lines, "==================================================================")
table.insert(lines, "  LUCIFER MULTIBOT — TÜM FONKSİYON VE API DÖKÜM RAPORU (OFFLINE)")
table.insert(lines, "  Oluşturan: Lucifer Deep Dumper v2.0 (mr_berk)")
table.insert(lines, "==================================================================\n")

-- 1. Globals
table.insert(lines, "--- [1. GLOBAL FONKSİYONLAR & NESNELER] ---")
local sorted_globals = {}
for k, v in pairs(dump.globals) do table.insert(sorted_globals, k) end
table.sort(sorted_globals)
for _, k in ipairs(sorted_globals) do
    table.insert(lines, string.format("  • %-30s : %s", k, dump.globals[k]))
end

-- 2. Enums
table.insert(lines, "\n--- [2. ENUMLAR (ENUMERATIONS)] ---")
local sorted_enums = {}
for k, _ in pairs(dump.enums) do table.insert(sorted_enums, k) end
table.sort(sorted_enums)
for _, ename in ipairs(sorted_enums) do
    table.insert(lines, string.format("\n  [Enum: %s]", ename))
    for k, v in pairs(dump.enums[ename]) do
        table.insert(lines, string.format("    - %-25s = %s", k, tostring(v)))
    end
end

-- 3. Bot Members
table.insert(lines, "\n--- [3. BOT NESNESİ METOT VE ÖZELLİKLERİ] ---")
local sorted_bot = {}
for k, _ in pairs(dump.bot_members) do table.insert(sorted_bot, k) end
table.sort(sorted_bot)
for _, m in ipairs(sorted_bot) do
    table.insert(lines, string.format("  • bot:%-28s [%s]", m, dump.bot_members[m]))
end

-- 4. Automations
table.insert(lines, "\n--- [4. OTOMASYON MOTORLARI & ALT NESNELER] ---")
for auto_name, members in pairs(dump.automations) do
    table.insert(lines, string.format("\n  [Nesne: %s]", auto_name))
    for k, v in pairs(members) do
        table.insert(lines, string.format("    • %-26s [%s]", k, v))
    end
end

-- 5. Managers
table.insert(lines, "\n--- [5. WORLD & PROXY YÖNETİCİLERİ] ---")
table.insert(lines, "  [WorldManager Metotları]:")
for k, v in pairs(dump.world_manager_members) do
    table.insert(lines, string.format("    • wm:%-26s [%s]", k, v))
end
table.insert(lines, "  [ProxyManager Metotları]:")
for k, v in pairs(dump.proxy_manager_members) do
    table.insert(lines, string.format("    • pm:%-26s [%s]", k, v))
end

-- 6. HttpClient
table.insert(lines, "\n--- [6. HTTP CLIENT & AĞ FONKSİYONLARI] ---")
for k, v in pairs(dump.http_client_members) do
    table.insert(lines, string.format("  • client:%-24s [%s]", k, v))
end

local txt_output = table.concat(lines, "\n")

-- Dosyalara Yaz (write)
if write then
    pcall(function()
        write("lucifer_dumped_api.txt", txt_output)
        print("✅ [BAŞARILI] 'lucifer_dumped_api.txt' oluşturuldu!")
    end)
end

-- JSON Serializer
local function toJson(val)
    local t = type(val)
    if t == "nil" then return "null"
    elseif t == "boolean" then return val and "true" or "false"
    elseif t == "number" then return tostring(val)
    elseif t == "string" then
        local esc = val:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
        return '"' .. esc .. '"'
    elseif t == "table" then
        local p = {}
        for k, v in pairs(val) do
            table.insert(p, '"' .. tostring(k):gsub('"', '\\"') .. '":' .. toJson(v))
        end
        return "{" .. table.concat(p, ",") .. "}"
    end
    return '"' .. tostring(val) .. '"'
end

local json_str = toJson(dump)
if write then
    pcall(function()
        write("lucifer_dumped_api.json", json_str)
        print("✅ [BAŞARILI] 'lucifer_dumped_api.json' oluşturuldu!")
    end)
end

-- Python Relay'e Bildir
if HttpClient and HttpClient.new then
    pcall(function()
        local client = HttpClient.new()
        client.method = Method.post
        client.url = RELAY_URL .. "/api/dump"
        client.body = json_str
        client:request()
        print("🚀 API dökümü yerel Python sunucusuna otomatik aktarıldı!")
    end)
end

print("----------------------------------------------------------")
print(string.format("  Global Fonksiyonlar  : %d adet", #sorted_globals))
print(string.format("  Bulunan Enum Sayisi  : %d adet", #sorted_enums))
print(string.format("  Bot Metod & Alanlari : %d adet", #sorted_bot))
print("==========================================================")
print("DÖKÜM TAMAMLANDI! Lucifer klasöründeki 'lucifer_dumped_api.txt' dosyasını açıp inceleyebilirsin!")
