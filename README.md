<div align="center">

# 😈 LUCIFER MCP

### Full-Access AI Control & Lua Tooling for Growtopia Lucifer v2.88 p2 — Model Context Protocol

**Author watermark: `mr_berk`**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.x-green.svg)](https://gofastmcp.com)
[![Lucifer](https://img.shields.io/badge/Lucifer-v2.88%20p2-purple.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

**63 MCP tools** · **6,833 real item IDs** · **3,808 splicing & mass recipes** · **44 BotStatus & 21 GoogleStatus codes** · **1:1 live minimap PNG** · **Synchronous Lua eval & live `[Logs]` capture**

*NOT FAKE — BUILT FROM REAL LUCIFER v2.88 p2 RUNTIME DUMPS & `items.dat` DATA*

🌐 **Language / Dil:** 🇺🇸 **English (Current)** | 🇹🇷 **[Türkçe Rehber (README_TR.md)](README_TR.md)**

📚 Documentation:
- [INSTALL.md](INSTALL.md) — Step-by-step English setup guide
- [KURULUM.md](KURULUM.md) — Adım adım Türkçe kurulum rehberi
- [AGENTS.md](AGENTS.md) — Bilingual AI instructions (auto-setup + rules)
- [AI_TRAINING.md](AI_TRAINING.md) — English Lucifer v2.88 p2 AI training pack
- [AI_EGITIM.md](AI_EGITIM.md) — Türkçe Lucifer v2.88 p2 AI eğitim paketi
- [UPDATING.md](UPDATING.md) / [GUNCELLEME.md](GUNCELLEME.md) — Update guides

</div>

---

## 🤖 Copy Link → Paste to Any AI (Just Works!)

When you paste `https://github.com/BrK08/lucifer-mcp` into an AI assistant:

- **AI with Terminal Access (Antigravity, Cursor, Claude Code, Windsurf, Cline):** It reads [`AGENTS.md`](AGENTS.md), clones the repo, installs requirements, launches `python start_mcp.py`, and gives you the 1-line Lucifer Executor command.
- **Cloud / Web AI (ChatGPT, Claude.ai Web/Mobile, Gemini):** It first walks you through the 3 commands below to get your `https://xxxx.trycloudflare.com/mcp` connector URL, and can immediately write 100% real Lucifer v2.88 p2 Lua scripts using [`AI_TRAINING.md`](AI_TRAINING.md).

---

## What this project is

**Lucifer MCP** connects your AI assistant directly to **Growtopia Lucifer Multibot v2.88 p2** through the Model Context Protocol (MCP). Once connected, an AI can operate your Lucifer bots just like a human inside the Lucifer GUI:

- Run synchronous Lua scripts (`luci_eval_sync`) and read `return` values + live `print(...)` / `[Console]` / `[Logs]` output
- Inspect live worlds, players, tiles, `TileExtra` growth/lock data, floating objects, and 1:1 minimap PNG renders (`luci_inspect_world`, `luci_inspect_tile`, `luci_world_count_item`, `luci_render_world_map`)
- Control movement, pathfinding, placing, punching, wrenching, doors, Magplant retrieval, store purchases, equipment, and raw packets
- Configure Lucifer subsystems (`Rotation`, `WorldManager`, `ProxyManager`, `AutoFarm`, `Trash & Pack Manager`, and `GLServer` Google Login settings)
- Look up any of **6,833 real Growtopia item IDs** and **3,808 splicing recipes**
- Analyze custom Lua code for ASCII safety, hallucinated APIs, and ban risk (`luci_code_analyze`, `luci_auto_test`) before running on live bots

---

## Quick start (One Command)

### 1) Clone and install

```bash
git clone https://github.com/BrK08/lucifer-mcp.git
cd lucifer-mcp
pip install -r requirements.txt
```

### 2) Start the MCP server (with Relay + Cloudflare HTTPS Tunnel)

```bash
python start_mcp.py
```

`start_mcp.py` automatically:
1. Detects/creates your `scripts/` folder and deploys `lucifer_bridge.lua`
2. Starts the Lucifer HTTP Relay at `http://127.0.0.1:8829`
3. Opens a free Cloudflare Quick Tunnel (`https://xxxx.trycloudflare.com/mcp`) if `cloudflared` is installed (optional for ChatGPT Web / Claude Connectors)
4. Starts the FastMCP Streamable HTTP server at `http://127.0.0.1:8828/mcp`

*(Use `python server.py` or `python start_mcp.py --stdio` for desktop/IDE `stdio` clients like Claude Desktop, Cursor, and Antigravity.)*

### 3) Connect your AI client

- **ChatGPT / Claude Web Connectors:** Paste the printed `https://xxxx.trycloudflare.com/mcp` URL into **Settings → Connectors → Add custom MCP**.
- **Claude Desktop / Cursor / VS Code / Antigravity:** See copy-paste JSON configs in [INSTALL.md](INSTALL.md).

### 4) Run the bridge once inside Lucifer

Open **Lucifer v2.88 p2 → Executor** tab and execute this 1-line loader:

```lua
local c = HttpClient.new(); c.url = "http://127.0.0.1:8829/bridge.lua"; local r = c:request(); load(r and r.body or c.content)()
```

*(Or open `scripts/lucifer_bridge.lua` inside Lucifer and click **Execute**.)*

---

## Architecture overview

```text
┌───────────────────┐   MCP (stdio / HTTP)    ┌─────────────────────┐   HTTP :8829    ┌───────────────────────┐
│ ChatGPT / Claude  │ ◄─────────────────────► │ server.py /         │ ◄─────────────► │ lucifer_bridge.lua    │
│ Cursor / Gemini   │       63 MCP tools      │ mcp_server/server.py│   /api/poll     │ (Inside Lucifer v2.88 │
└───────────────────┘                         │ & core/relay_server │   /api/result   │  p2 Lua Runtime)      │
                                              └─────────────────────┘                 └───────────────────────┘
```

- **Offline Knowledge & Safety Tools** work immediately even before Lucifer is open.
- **Live Bridge Tools** execute synchronously over the local `127.0.0.1:8829` relay using Lucifer's native `HttpClient.new()`.

---

## Included tools (63 MCP Tools)

| Category | Tools | What it does |
|---|---|---|
| **Live Script & Console** | `luci_eval_sync`, `luci_run_script`, `luci_stop_script`, `luci_auto_test`, `luci_get_console_and_logs`, `luci_get_bot_logs`, `luci_code_analyze` | Synchronous Lua execution with return & print capture, live `[Console]`/`[Logs]` inspection, ban-risk & ASCII check |
| **World, Tile & Minimap** | `luci_inspect_world`, `luci_inspect_tile`, `luci_world_count_item`, `luci_render_world_map` | Players, dropped objects, tile FG/BG/TileExtra, live item counting, 1:1 PNG minimap render |
| **Fleet & Inventory** | `luci_fleet_status`, `luci_bot_list`, `luci_bot_inventory`, `luci_fleet_census` | Live multi-bot status, gems, ping, levels, full fleet inventory census |
| **Human-Equivalent Actions** | `luci_warp`, `luci_say`, `luci_move`, `luci_find_path`, `luci_find_world_path`, `luci_enter_door`, `luci_leave_world`, `luci_respawn`, `luci_place_block`, `luci_punch_tile`, `luci_wrench`, `luci_activate_tile`, `luci_collect`, `luci_drop_item`, `luci_trash_item`, `luci_equipment`, `luci_buy`, `luci_retrieve`, `luci_send_packet`, `luci_send_raw_packet` | Every GUI/player action: movement, A* pathfinding, blocks, doors, wrench, Magplant retrieve, wear/use, raw packets |
| **Bot & Subsystems** | `luci_add_bot`, `luci_remove_bot`, `luci_connect_bot`, `luci_disconnect_bot`, `luci_update_bot_identity`, `luci_set_automation`, `luci_set_setting`, `luci_setup_farm`, `luci_configure_rotation`, `luci_world_manager`, `luci_configure_subsystem`, `luci_proxy_manager`, `luci_set_bot_proxy`, `luci_assign_proxies_bulk`, `luci_proxy_next`, `luci_trash_and_pack_manager` | Account lifecycle, AutoFarm/AutoCollect/AntiMod settings, Rotation, WorldManager, ProxyManager, Trash/Pack rules |
| **Item DB, Docs & GLServer** | `luci_search_item`, `luci_item_details`, `luci_api_docs`, `luci_file_system`, `luci_analyze_risk`, `luci_diagnose_status`, `luci_bot_google_status`, `luci_glserver_info`, `luci_glserver_set`, `luci_glserver_captcha_guide`, `luci_glserver_parse_response`, `luci_relay_info` | 6,833 Growtopia items, splicing recipes, Lucifer runtime docs search, local script files, GLServer diagnostics |

---

## Data sources

| Source | Contents |
|---|---|
| `docs/lucifer_dumped_api.json` & `.txt` | Runtime-dumped Lucifer v2.88 p2 functions, methods, classes, and properties |
| `docs/functions.md`, `structs.md`, `enums.md`, `automations.md`, `rotation.md` | Complete Lucifer API & enum reference (44 `BotStatus`, 21 `GoogleStatus`) |
| `data/items.json` & `data/recipes.json` | 6,833 Growtopia item IDs and 3,808 splicing recipes/growth metadata |

---

## Responsibility notice

This project is provided for educational, research, and automation tooling purposes under the [MIT License](LICENSE). Growtopia's Terms of Service prohibit third-party bots/automation; always use safely and at your own discretion.

<div align="center">

### 👑 mr_berk

`Lucifer MCP` — 63 tools · 6,833 real Growtopia item IDs · 3,808 recipes

</div>
