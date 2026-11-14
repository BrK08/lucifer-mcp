# 🔄 Updating & Lucifer Version Compatibility Guide — Lucifer MCP

> **Short answer:** Most Lucifer updates break nothing — because Lucifer MCP talks through Lua's runtime bridge (`bridge/lucifer_bridge.lua`) and keeps API/item metadata inside editable JSON and Markdown files.

<div align="center">
👑 <b>mr_berk</b> edition · <b>63 MCP tools</b> · <b>6,833 real item IDs</b> · <b>3,808 recipes</b>
</div>

---

## 1. Updating Lucifer MCP (`git pull`)

```bash
cd lucifer-mcp
git pull
pip install -r requirements.txt
```

Then restart `python start_mcp.py` (or restart your stdio client such as Claude Desktop / Cursor) and re-run the 1-line bridge inside Lucifer Executor.

---

## 2. When a New Lucifer Version Releases

| Scenario | What happens | What to do |
|---|---|---|
| **Minor Lucifer update** | Existing Lua bridge keeps working as-is | Run quick health check (`luci_fleet_status`, `luci_eval_sync("return 1+1")`) |
| **New Growtopia items added** | Old `items.json` lacks newest IDs | Run `tools/generate_gt_items.py` / update `data/items.json` & `data/recipes.json` |
| **New Lucifer Lua functions added** | Missing from local docs search | Run `tools/lucifer_api_dumper.lua` inside Lucifer and update `docs/` |

---

## 3. 2-Minute Health Check After Updating

1. Run `python start_mcp.py` (or `--stdio`).
2. Paste the 1-line bridge loader in **Lucifer → Executor**:
   ```lua
   local c = HttpClient.new(); c.url = "http://127.0.0.1:8829/bridge.lua"; local r = c:request(); load(r and r.body or c.content)()
   ```
3. Ask your AI to run:
   - `luci_relay_info()` → confirms Relay port & bridge readiness
   - `luci_fleet_status()` → confirms live bot heartbeats
   - `luci_eval_sync("return getBot() and getBot():name() or 'NO_BOT'")` → confirms synchronous execution

If all three succeed, everything is 100% compatible!
