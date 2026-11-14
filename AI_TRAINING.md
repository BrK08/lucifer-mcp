# 🧠 LUCIFER v2.88 p2 AI TRAINING PACK — `mr_berk` edition

> **Paste this file into ANY AI (ChatGPT, Claude, Gemini, DeepSeek, Cursor...) and it will immediately write 100% VALID Lucifer v2.88 p2 Lua scripts.**
> Everything below is verified from real Lucifer v2.88 p2 runtime dumps (`docs/lucifer_dumped_api.txt` & `docs/AI_TRAINING_LUCIFER.md`) and `items.dat` (6,833 item IDs). There is ZERO invented syntax here.

---

## 0) How to Use This Pack

- **With Live MCP Connected (Recommended):** Run `python start_mcp.py`, connect `https://xxxx.trycloudflare.com/mcp` (or `server.py` via stdio), and run the 1-line bridge inside Lucifer Executor. The AI will inspect live worlds/inventories/logs and run `luci_eval_sync` / `luci_auto_test` directly.
- **Without MCP (Pure Chat Mode):** Paste this file into a new ChatGPT / Claude / Gemini conversation (or Custom GPT / Project Knowledge) and ask for any Lucifer Lua script.

---

## 1) Critical Rules & Anti-Hallucination Checklist

1. **You Are Coding for LUCIFER v2.88 p2 — NOT GentaHAX!**
   - **NEVER use GentaHAX APIs** (they do NOT exist in Lucifer):
     - `AddHook` → **WRONG** (use Lucifer's `addEvent` / `listenEvents` / `removeEvent`)
     - `makeRequest` → **WRONG** → Use `HttpClient.new()`
     - `requestTileChange(x, y, id)` → **WRONG** → Use `bot:place(x, y, id)` or `bot:hit(x, y)`
     - `checkTile` / `getTile` global → **WRONG** → Use `world:getTile(x, y)`
     - `getLocal()` → **WRONG** → Use `getBot()` / `world:getLocal()`
     - `bot:getBotStatus()` → **WRONG (CRASH!)** → `bot.status` is a **numeric property** (`0..44`), NOT a method!
     - `world:getDoors()` → **WRONG (DOES NOT EXIST)** → Scan `world:getTiles()` for `tile.fg == 6` or `tile.fg == 12`, or warp directly with `bot:warp("WORLD", "DOORID")`
     - `world:name()` → **WRONG** → `world.name` is a **string property**, NOT a method!
     - Dividing `bot.x / 32` → **WRONG** → `bot.x` and `bot.y` are ALREADY tile coordinates (`0..99`, `0..59`)!
2. **Strict 7-Bit ASCII Inside All Lua Code:**
   - Growtopia and Lucifer's console do **NOT** render Turkish/non-ASCII glyphs (`ğ, ü, ş, ı, ö, ç, İ, Ğ, Ü, Ş, Ö, Ç`).
   - All strings inside Lua (`print`, `bot:say`, `Log`, dialogs, packets) MUST be pure 7-bit ASCII.
3. **Mandatory Script Header:**
   ```lua
   -- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
   ```
4. **Always Add Randomized Jitter Delays (`sleep`):**
   - Never use `while true do` without `sleep()` (freezes Lucifer).
   - Never use fixed robotic timings; always add `math.random(...)`:
     - Punch / Hit: `sleep(170 + math.random(15, 45))`
     - Place: `sleep(145 + math.random(15, 35))`
     - Collect: `sleep(160 + math.random(20, 50))`
     - Drop / Trash: `sleep(350 + math.random(50, 100))`
     - Warp: `sleep(3500 + math.random(200, 600))`
5. **Mandatory Null Guards & Edge Checks:**
   - Always check `local world = bot:getWorld(); if not world then sleep(1000) return end`
   - Always verify inventory count before calling `bot:place(x, y, id)`
   - Only harvest trees when `tile:canHarvest() == true`
   - Check `bot.status == 22` (`mod_entered`) to escape immediately and `bot.status == 43` (`banwave_detected`) to pause!
6. **Pre-Run Verification with MCP:**
   - Run `luci_code_analyze` before executing custom scripts on live bots.
   - Use `luci_eval_sync` or `luci_auto_test` + `luci_get_console_and_logs` to read real output.

---

## 2) Verified Lucifer v2.88 p2 Bot Methods & Properties

```lua
-- Multibot selectors
local bot = getBot()                  -- Current bot instance
local bots = getBots()                -- All bots in Lucifer fleet

-- Core status & movement properties
bot.status                            -- BotStatus integer (0..44) — property, NOT method!
bot.x, bot.y                          -- Current tile coordinates (0..99, 0..59)

-- Core Control
bot:name()                            -- Bot GrowID / name
bot:status()                          -- (Note: bot.status property is safest across builds)
bot:google_status()                   -- GoogleStatus int code (0..21)
bot:connect()                         -- Connect bot to Growtopia
bot:disconnect()                      -- Disconnect bot
bot:warp(world, door_id)              -- Warp to world (optional door_id)
bot:leaveWorld()                      -- Exit current world
bot:respawn()                         -- Respawn bot at white door
bot:say(text)                         -- Send chat bubble/message
bot:gem_count()                       -- Current gems
bot:level()                           -- Bot level
bot:getPing()                         -- Latency in ms
bot:getCaptcha()                      -- Captcha challenge URL
bot:getInventory()                    -- Inventory object (:getItems())
bot:getWorld()                        -- World object

-- Movement & World Actions
bot:findPath(x, y)                    -- Pathfind & walk to tile (x, y)
bot:moveTo(dx, dy)                    -- Step relative offset
bot:place(x, y, item_id)              -- Place block or plant seed at (x, y)
bot:hit(x, y)                         -- Punch tile (x, y)
bot:wrench(x, y)                      -- Wrench tile (x, y)
bot:wrenchPlayer(netid)               -- Wrench player by netid
bot:collect(range, interval)          -- Collect dropped objects in range
bot:collectByID(id)                   -- Collect specific item ID
bot:collectObject(uid)                -- Collect specific object UID
bot:drop(id, count)                   -- Drop item
bot:fastDrop(id, count)               -- Fast drop item
bot:trash(id, count)                  -- Trash item
bot:fastTrash(id, count)              -- Fast trash item
bot:wear(id)                          -- Equip/wear clothing or tool
bot:unwear(id)                        -- Unequip item
bot:use(id)                           -- Consume/use item
bot:buy(item_id, count, max_price)    -- Buy from Vend / Store

-- Safety & Toggles
bot:legit_mode(bool)
bot:anti_fire(bool)
bot:anti_toxic(bool)
bot:ignore_gems(bool)
bot:auto_reconnect(bool)
bot:auto_leave_on_mod(bool)
bot:auto_leave_on_admin(bool)
```

---

## 3) World, Tile, TileExtra, Player, Inventory & Item Objects

- **`World` (`local world = bot:getWorld()`):**
  - `world.name` (string), `world.x` (100), `world.y` (60), `world.weather`
  - `world:hasAccess()` (bool), `world:getTile(x, y)`, `world:getTiles()`, `world:getTilesSafe()`, `world:getPlayers()`, `world:getObjects()`
- **`Tile` (`local tile = world:getTile(x, y)`):**
  - `tile.x`, `tile.y`, `tile.fg`, `tile.bg`, `tile.flags`
  - `tile:canHarvest()` (bool — true when tree is ripe!)
  - `tile:hasExtra()`, `tile:getExtra()`
- **`TileExtra` (`local extra = tile:getExtra()`):**
  - `extra.id`, `extra.count`, `extra.growth` (seconds elapsed since planting), `extra.flags`
- **`Player` (`world:getPlayers()`):**
  - `player.name`, `player.netid`, `player.userid`, `player.country`, `player.clothes`
- **`Inventory` (`local inv = bot:getInventory(); for _, item in pairs(inv:getItems()) do ... end`):**
  - `item.id`, `item.count`, `item.isActive`
- **`ItemDescription` (`local info = getInfo(id)`):**
  - `info.id`, `info.name`, `info.rarity`, `info.growth`, `info.flags`

---

## 4) HttpClient Syntax (Official Lucifer Pattern)

```lua
-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp
local client = HttpClient.new()
client.url = "http://127.0.0.1:8829/api/status"
client.method = Method.get
local res = client:request()
if res and res.body then
    print("Response: " .. tostring(res.body))
end
```

---

## 5) Key BotStatus & GoogleStatus Codes

- **`BotStatus` (`bot.status`):** `0=offline`, `1=online`, `2=wrong_password`, `3=account_banned`, `4=account_suspended`, `5=location_banned`, `7=advanced_account_protection`, `10=maintenance`, `13=http_block`, `21=captcha_requested`, `22=mod_entered`, `30=could_not_warp`, `34=retrieving_token`, `35=two_factor`, `41=solving_captcha`, `42=failed_captcha`, `43=banwave_detected`
- **`GoogleStatus` (`bot:google_status()`):** `0=idle`, `1=processing`, `4=invalid_key`, `5=missing_server`, `10=invalid_credentials`, `13=captcha_required`, `16=otp_required`, `21=redirect`

*(Need the full 44 BotStatus + 21 GoogleStatus table or Automation/Rotation objects? See `docs/AI_TRAINING_LUCIFER.md`, `docs/enums.md`, `docs/functions.md`, `docs/automations.md`, `docs/rotation.md`, or call `luci_api_docs`.)*

---

## 6) Common Verified Growtopia Item IDs (Sample from 6,833 Items)

| Item | Block ID | Seed ID |
|---|---|---|
| Dirt | `2` | `3` |
| Lava | `4` | `5` |
| Wooden Door | `6` | `7` |
| Rock | `10` | `11` |
| Door | `12` | `13` |
| Cave Background | `14` | `15` |
| Small Lock / Big Lock / Huge Lock | `202` / `204` / `206` | `203` / `205` / `207` |
| World Lock | `242` | `243` |
| Chandelier | `340` | `341` |
| Diamond Lock | `1796` | `—` |
| Fish Tank | `3004` | `3005` |
| Pepper Tree | `4584` | `4585` |
| MAGPLANT 5000 | `5638` | `—` |
| Laser Grid | `5666` | `5667` |
| Blue Gem Lock | `7188` | `—` |

*(Never guess IDs — look up any of 6,833 items via `luci_search_item` or `luci_item_details`!)*
