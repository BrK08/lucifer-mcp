#!/usr/bin/env python3
"""
LUCIFER Multibot Control Deck — FastAPI Gateway & Real-time WS Server
Implements REST surface over SQLite (auth, audit logs, bot profiles) with
WebSocket fan-out and direct bridge to core.bot_manager.fleet_manager.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

# Ensure root lucifer-mcp is in python path
ROOT = Path(__file__).resolve().parent.parent
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bot_manager import fleet_manager
from core.minimap_renderer import render_minimap_bytes
from core.item_db import get_all_items_catalog, get_item_name
from core.tenant_manager import render_bridge_lua, tenant_manager

DB_PATH = ROOT / "data" / "lucifer_deck.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
INDEX_HTML_PATH = Path(__file__).resolve().parent / "index.html"


# =====================================================================
# Database Initialization & Helpers
# =====================================================================
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            token TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            details TEXT
        );

        CREATE TABLE IF NOT EXISTS bot_profiles (
            name TEXT PRIMARY KEY,
            proxy TEXT,
            world TEXT,
            status TEXT DEFAULT 'offline',
            farm_config TEXT,
            auto_settings TEXT,
            updated_at REAL NOT NULL
        );
        """)
        # Insert default admin user if missing
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (username, token, created_at) VALUES (?, ?, ?)",
                ("admin", "lucifer-deck-secret-token", time.time()),
            )
    conn.close()


init_db()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


ws_hub = ConnectionManager()


# Register event subscriber with fleet_manager for real-time WebSocket push
def on_fleet_event(event_type: str, data: Dict[str, Any]):
    asyncio.create_task(ws_hub.broadcast({"event": event_type, "data": data}))


fleet_manager.subscribe_event(on_fleet_event)


import os

# Background task for periodic fleet summary fan-out using modern lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()

    async def poll_broadcaster():
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2.0)
                break
            except asyncio.TimeoutError:
                pass
            if ws_hub.active_connections:
                summary = fleet_manager.get_fleet_summary()
                await ws_hub.broadcast(summary)

    task = asyncio.create_task(poll_broadcaster())

    # Auto-start Discord bot if configured
    discord_task = None
    try:
        from run_discord_bot import load_config
        cfg = load_config()
        discord_cfg = cfg.get("discord", {})
        token = os.environ.get("DISCORD_TOKEN") or discord_cfg.get("token")
        if discord_cfg.get("enabled", True) and token and token not in ("YOUR_DISCORD_BOT_TOKEN_HERE", ""):
            from discord_bot.bot import LuciferDiscordBot
            bot = LuciferDiscordBot(config=discord_cfg)
            discord_task = asyncio.create_task(bot.start(token))
            print("🚀 [WebDeck] Discord Bot auto-launched in integrated process mode!")
    except Exception as e:
        print(f"[WebDeck] Discord Bot auto-launch skipped: {e}")

    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        if discord_task:
            discord_task.cancel()


from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Lucifer Multibot Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ASSETS_PATH = ROOT / "assets"
if ASSETS_PATH.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_PATH)), name="assets")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# =====================================================================
# Pydantic Schemas
# =====================================================================
class BotCommandRequest(BaseModel):
    type: str
    x: Optional[int] = None
    y: Optional[int] = None
    world: Optional[str] = None
    action: Optional[str] = None
    key: Optional[str] = None
    msg: Optional[str] = None
    id: Optional[int] = None
    n: Optional[int] = None


class ProfileRequest(BaseModel):
    name: str
    proxy: Optional[str] = ""
    world: Optional[str] = ""
    farm_config: Optional[Dict[str, Any]] = None
    auto_settings: Optional[Dict[str, Any]] = None


class FleetBroadcastRequest(BaseModel):
    action: Optional[str] = None
    command: Optional[str] = None
    type: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    filter_online: Optional[bool] = True
    bots: Optional[List[str]] = None
    world: Optional[str] = None


# =====================================================================
# Web Deck Static & UI Serving
# =====================================================================
@app.get("/", response_class=HTMLResponse)
async def serve_deck():
    if not INDEX_HTML_PATH.exists():
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    return HTMLResponse(INDEX_HTML_PATH.read_text(encoding="utf-8"))


@app.get("/bridge.lua")
async def serve_bridge_lua(
    request: Request,
    token: Optional[str] = None,
    relay: Optional[str] = None,
):
    bridge_path = ROOT / "bridge" / "lucifer_bridge.lua"
    if not bridge_path.exists():
        raise HTTPException(status_code=404, detail="lucifer_bridge.lua not found")

    server_url = str(relay or "").strip()
    if not server_url:
        host_hdr = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        if host_hdr:
            proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
            server_url = f"{proto}://{host_hdr}"

    content = render_bridge_lua(bridge_path, token=token, server_url=server_url)
    return Response(content, media_type="text/plain")


# =====================================================================
# WebSocket Endpoint
# =====================================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_hub.connect(websocket)
    # Send immediate initial summary upon connection
    await websocket.send_text(json.dumps(fleet_manager.get_fleet_summary()))
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming ping / client-side commands if any
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "time": time.time()}))
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_hub.disconnect(websocket)


def _sanitize_bot_name(raw_name: Any, default: str = "unknown") -> str:
    """Sanitizes raw bot name against unhashable or non-string types."""
    if isinstance(raw_name, str):
        cleaned = raw_name.strip()
        return cleaned if cleaned else default
    if isinstance(raw_name, (int, float)):
        return str(raw_name)
    if isinstance(raw_name, (list, tuple, dict)):
        try:
            val = str(raw_name).strip()
            return val if val else default
        except Exception:
            return default
    return default


# =====================================================================
# Bridge Telemetry & Command Relay Endpoints (/api/heartbeat & /api/poll)
# =====================================================================
@app.post("/api/heartbeat")
async def post_heartbeat(request: Request):
    """
    Receives live telemetry heartbeat from Lucifer bots running bridge/lucifer_bridge.lua
    or external automation clients. Updates fleet_manager state and returns immediate queued commands.
    """
    try:
        data = await request.json()
    except Exception:
        body = await request.body()
        if body:
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")
        else:
            raise HTTPException(status_code=400, detail="Empty request body")

    if not isinstance(data, (dict, list)):
        raise HTTPException(status_code=400, detail="JSON payload must be an object or list")

    query_token = str(request.query_params.get("token", "") or "").strip()

    if isinstance(data, list):
        results = {}
        for item in data:
            if isinstance(item, dict):
                clean = dict(item)
                clean.pop("owner_id", None)
                if query_token and not clean.get("owner_token") and not clean.get("token"):
                    clean["owner_token"] = query_token
                raw_name = clean.get("bot_name")
                if raw_name is None:
                    raw_name = clean.get("name")
                if raw_name is None:
                    raw_name = clean.get("bot")
                b_name = _sanitize_bot_name(raw_name)
                clean["name"] = b_name
                clean["bot_name"] = b_name
                if "gems" in clean and "gem_count" not in clean:
                    clean["gem_count"] = clean["gems"]
                bot = fleet_manager.update_heartbeat(clean)
                results[bot.name] = fleet_manager.pop_commands_for_bot(
                    bot.name, owner_id=bot.owner_id
                )
        return {"status": "ok", "fleet_size": len(data), "commands": results}

    # Single bot payload
    clean_single = dict(data)
    clean_single.pop("owner_id", None)
    if query_token and not clean_single.get("owner_token") and not clean_single.get("token"):
        clean_single["owner_token"] = query_token

    raw_name = clean_single.get("bot_name")
    if raw_name is None:
        raw_name = clean_single.get("name")
    if raw_name is None:
        raw_name = clean_single.get("bot")
    bot_name = _sanitize_bot_name(raw_name)
    clean_single["name"] = bot_name
    clean_single["bot_name"] = bot_name
    if "gems" in clean_single and "gem_count" not in clean_single:
        clean_single["gem_count"] = clean_single["gems"]

    bot = fleet_manager.update_heartbeat(clean_single)
    commands = fleet_manager.pop_commands_for_bot(bot.name, owner_id=bot.owner_id)
    return {
        "status": "ok",
        "bot": bot.name,
        "commands": commands,
    }


@app.post("/api/command_result")
async def post_command_result(request: Request):
    """Receives synchronous command/eval results from bridge/lucifer_bridge.lua."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                fleet_manager.record_command_result(entry)
        return {"status": "ok", "recorded": len(data)}
    if isinstance(data, dict):
        fleet_manager.record_command_result(data)
        return {"status": "ok", "cmd_id": data.get("cmd_id", "")}
    raise HTTPException(status_code=400, detail="Payload must be object or list")


@app.get("/api/poll")
async def get_poll(bot: Optional[str] = "global", token: Optional[str] = None):
    """
    Polls queued commands for a specific bot or global fleet commands.
    """
    bot_name = _sanitize_bot_name(bot, default="global")
    owner_id = tenant_manager.resolve_user_by_token(token) if token else None
    commands = fleet_manager.pop_commands_for_bot(bot_name, owner_id=owner_id)
    first_cmd = commands[0] if commands else None
    action = first_cmd.get("action", "") if isinstance(first_cmd, dict) else ""
    cmd_params = first_cmd.get("params", {}) if isinstance(first_cmd, dict) else {}
    if not isinstance(cmd_params, dict):
        cmd_params = {}
    code = cmd_params.get("code", "") if isinstance(cmd_params, dict) else ""

    return {
        "status": "ok",
        "bot": bot_name,
        "commands": commands,
        "command": action,
        "script": code,
    }


# =====================================================================
# Fleet & Bot REST Endpoints (Compatible with Deck UI)
# =====================================================================
@app.get("/api/fleet/summary")
@app.get("/fleet/summary")
async def get_fleet_summary(owner_id: Optional[str] = None, token: Optional[str] = None):
    eff_owner = tenant_manager.resolve_user_by_token(token) if token else owner_id
    return fleet_manager.get_fleet_summary(owner_id=eff_owner)


@app.get("/api/fleet/stats")
async def get_fleet_stats(owner_id: Optional[str] = None, token: Optional[str] = None):
    """
    Returns enriched fleet activity metrics and resource aggregation summary.
    """
    eff_owner = tenant_manager.resolve_user_by_token(token) if token else owner_id
    activity = fleet_manager.get_fleet_activity_stats(owner_id=eff_owner)
    inventory = fleet_manager.get_fleet_inventory_summary(owner_id=eff_owner)

    return {
        "status": "ok",
        "activity": activity,
        "inventory": inventory,
        "total_bots": activity.get("total_bots", 0),
        "online_bots": activity.get("online_bots", 0),
        "offline_bots": activity.get("offline_bots", 0),
        "total_gems": inventory.get("total_gems", 0),
        "total_items": inventory.get("total_items", 0),
        "world_distribution": activity.get("world_distribution", {}),
        "status_breakdown": activity.get("status_breakdown", {}),
        "uptime": activity.get("uptime", {}),
        "active_farming_bots": activity.get("active_farming_bots", 0),
        "worlds": activity.get("worlds", []),
        "average_ping": activity.get("average_ping", 0.0),
        "captcha_alerts": activity.get("captcha_alerts", 0),
        "http_blocked_bots": activity.get("http_blocked_bots", 0),
    }


@app.post("/api/command")
@app.post("/api/fleet/broadcast")
async def post_fleet_broadcast(request: Request):
    """
    Broadcasts or targets a command to bots in the fleet.
    Accepts JSON payload with action/command, params, filter_online, and optional bot list.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON payload must be an object")

    action = data.get("action") or data.get("command") or data.get("type")
    if not action or not isinstance(action, str) or not action.strip():
        raise HTTPException(status_code=400, detail="Action is required for command")

    action = action.strip()
    raw_params = data.get("params")
    if not isinstance(raw_params, dict):
        params = {}
    else:
        params = dict(raw_params)

    # Allow top-level parameters such as 'world' to be inherited by params
    if "world" in data and data["world"] and "world" not in params:
        params["world"] = data["world"]

    tok = str(data.get("owner_token") or request.query_params.get("token", "") or "").strip()
    eff_owner = tenant_manager.resolve_user_by_token(tok) if tok else data.get("owner_id")

    target_bot = data.get("bot") or data.get("bot_name")
    if target_bot and target_bot != "all":
        cmd_id = fleet_manager.queue_command(
            bot_name=str(target_bot),
            action=action,
            params=params,
            owner_id=eff_owner,
        )
        if not cmd_id:
            raise HTTPException(status_code=404, detail=f"Bot '{target_bot}' not found or unauthorized")
        return {"status": "ok", "bot": str(target_bot), "action": action, "targeted": 1, "command_id": cmd_id}

    filter_online = data.get("filter_online", True)
    if not isinstance(filter_online, bool):
        filter_online = True

    bots = data.get("bots")
    if bots is not None and not isinstance(bots, list):
        bots = None

    targeted = fleet_manager.queue_broadcast_command(
        action=action,
        params=params,
        filter_online=filter_online,
        bot_names=bots,
        owner_id=eff_owner,
    )

    # Log to audit trail
    try:
        conn = get_db()
        with conn:
            conn.execute(
                "INSERT INTO audit_logs (timestamp, actor, action, target, details) VALUES (?, ?, ?, ?, ?)",
                (
                    time.time(),
                    "web_deck",
                    f"broadcast_{action}",
                    "fleet",
                    json.dumps({"params": params, "targeted": targeted, "filter_online": filter_online}),
                ),
            )
        conn.close()
    except Exception:
        pass

    return {
        "status": "ok",
        "action": action,
        "targeted_bots": targeted,
        "filter_online": filter_online,
        "params": params,
    }


@app.post("/api/execute")
async def post_execute_sync(request: Request):
    """Queue a command and await its live execution result from lucifer_bridge.lua."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON payload must be an object")

    action = str(data.get("action") or data.get("command") or data.get("type") or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail="Action is required")

    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    tok = str(data.get("owner_token") or request.query_params.get("token", "") or "").strip()
    if tok:
        eff_owner = tenant_manager.resolve_user_by_token(tok) or "__invalid_token__"
    else:
        raw_owner = data.get("owner_id") or request.query_params.get("owner_id")
        eff_owner = str(raw_owner).strip() if raw_owner else None

    try:
        timeout = max(0.5, min(float(data.get("timeout", 12.0)), 60.0))
    except (TypeError, ValueError):
        timeout = 12.0

    bot_name = str(data.get("bot") or data.get("bot_name") or "first").strip()
    if bot_name.lower() == "first":
        candidates = fleet_manager.list_bots(owner_id=eff_owner)
        online = [b for b in candidates if b.is_alive or b.status == "online"]
        picked = (online or candidates)[0] if candidates else None
        if not picked:
            return {"ok": False, "error": "No bots connected to relay."}
        bot_name = picked.name

    return await fleet_manager.aexecute_and_wait(
        bot_name=bot_name,
        action=action,
        params=params,
        timeout=timeout,
        owner_id=eff_owner,
    )


@app.get("/api/bot/{name}")
async def get_bot_detail(name: str):
    bot = fleet_manager.get_bot(name)
    if not bot:
        # Check SQLite profile if offline bot
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM bot_profiles WHERE name = ?", (name,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "name": row["name"],
                "status": row["status"] or "offline",
                "world": row["world"] or "",
                "gems": 0,
                "pearls": 0,
                "level": 1,
                "ping": 0,
                "x": 0,
                "y": 0,
                "automations": json.loads(row["auto_settings"] or "{}"),
            }
        raise HTTPException(status_code=404, detail=f"Bot '{name}' not found")

    return {
        "name": bot.name,
        "status": bot.status,
        "raw_status": bot.raw_status,
        "world": bot.world,
        "x": bot.x,
        "y": bot.y,
        "gems": bot.gem_count,
        "pearls": bot.pearl_count,
        "voucher_count": bot.voucher_count,
        "level": bot.level,
        "ping": bot.ping,
        "captcha_status": bot.captcha_status,
        "google_status": bot.google_status,
        "automations": bot.automations,
        "last_seen": bot.last_seen,
    }


@app.get("/api/items")
async def get_items_catalog():
    return get_all_items_catalog()


@app.get("/api/bot/{name}/inventory")
async def get_bot_inventory(name: str):
    bot = fleet_manager.get_bot(name)
    if not bot:
        return {"items": []}
    items = []
    if isinstance(bot.inventory, list):
        for it in bot.inventory:
            if isinstance(it, dict):
                iid = it.get("id", 0)
                entry = dict(it)
                if not entry.get("name"):
                    entry["name"] = get_item_name(iid)
                items.append(entry)
            else:
                items.append(it)
    return {"items": items}


@app.get("/api/bot/{name}/logs")
async def get_bot_logs(name: str):
    bot = fleet_manager.get_bot(name)
    if not bot:
        return {"logs": ""}
    return {"logs": bot.logs or f"[SYS] Bot {name} connected\n[SYS] Ready"}


@app.get("/api/bot/{name}/map")
async def get_bot_map(name: str):
    bot = fleet_manager.get_bot(name)
    world_name = bot.world if bot else "START"
    x = bot.x if bot else 50
    y = bot.y if bot else 23
    tiles = bot.tiles if bot else None
    other_players = bot.other_players if bot else None
    img_bytes = render_minimap_bytes(
        tiles=tiles,
        bot_x=x,
        bot_y=y,
        world_name=world_name,
        is_public=True,
        other_players=other_players,
    )
    return Response(content=img_bytes, media_type="image/png")


@app.post("/api/bot/{name}/cmd")
async def post_bot_cmd(name: str, cmd: BotCommandRequest):
    # Log command into audit trail
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO audit_logs (timestamp, actor, action, target, details) VALUES (?, ?, ?, ?, ?)",
            (time.time(), "web_deck", cmd.type, name, json.dumps(cmd.dict(exclude_none=True))),
        )
    conn.close()

    # Route command to bot manager
    action = cmd.type
    params = cmd.dict(exclude_none=True)
    cmd_id = fleet_manager.queue_command(bot_name=name, action=action, params=params)
    return {"status": "ok", "command_id": cmd_id, "action": action, "target": name}


# =====================================================================
# Audit Logs & Profiles Endpoints
# =====================================================================
@app.get("/api/audit")
async def get_audit_logs(limit: int = 50):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/profiles")
async def list_profiles():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bot_profiles ORDER BY name ASC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/profiles")
async def save_profile(profile: ProfileRequest):
    conn = get_db()
    with conn:
        conn.execute(
            """
            INSERT INTO bot_profiles (name, proxy, world, farm_config, auto_settings, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                proxy=excluded.proxy,
                world=excluded.world,
                farm_config=excluded.farm_config,
                auto_settings=excluded.auto_settings,
                updated_at=excluded.updated_at
            """,
            (
                profile.name,
                profile.proxy or "",
                profile.world or "",
                json.dumps(profile.farm_config or {}),
                json.dumps(profile.auto_settings or {}),
                time.time(),
            ),
        )
    conn.close()
    return {"status": "ok", "bot": profile.name}


# =====================================================================
# Standalone Runner
# =====================================================================
if __name__ == "__main__":
    import uvicorn
    print("🚀 [WebDeck] Launching Lucifer Control Deck Server on http://127.0.0.1:8829")
    uvicorn.run(app, host="127.0.0.1", port=8829, log_level="info")
