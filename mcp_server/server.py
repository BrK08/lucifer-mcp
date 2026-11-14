"""
Lucifer Multibot — FastMCP Server (Full Human-Equivalent Lucifer Control)
Exposes tools for AI assistants to control Growtopia Lucifer bots just like
a human user inside the Lucifer GUI: synchronous Lua execution with output/error
capture, live console & [Logs] reading, world/tile/object/player inspection,
movement/pathfinding/door/wrench/packet actions, full subsystem/Rotation/
WorldManager/ProxyManager/Trash&Pack configuration, Growtopia Item DB & docs.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from fastmcp import FastMCP

from core.bot_manager import fleet_manager
from core.enums import (
    Action,
    BotStatus,
    GoogleStatus,
    Platform,
    describe_bot_status,
    describe_google_status,
)
from core.evren_client import sanitize_lua_ascii, validate_lua_ascii
from core.glserver_client import glserver_client
from core.item_db import (
    get_block_id,
    get_item_details,
    get_item_id,
    get_item_name,
    get_seed_id,
    search_items,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
CONFIG_PATH = PROJECT_ROOT / "config.json"

mcp = FastMCP(
    name="Lucifer Multibot MCP Server",
    instructions=(
        "Full-access Lucifer v2.88 p2 Multibot Controller for Growtopia. "
        "Supports synchronous Lua execution with return/print capture (luci_eval_sync), "
        "live console/log inspection (luci_get_console_and_logs), live world/tile/object "
        "inspection (luci_inspect_world, luci_inspect_tile, luci_world_count_item), "
        "all human interactions (move, pathfind, enter_door, wrench, buy, retrieve, "
        "wear/use, packets), Rotation/WorldManager/ProxyManager/Subsystem settings, "
        "Growtopia Item DB, and Lucifer API documentation lookup."
    ),
)

# ---------------------------------------------------------------------------
# Relay Runtime Management (In-process or External Process HTTP Fallback)
# ---------------------------------------------------------------------------
_RELAY_LOCK = threading.Lock()
_INPROCESS_RELAY_SERVER: Any = None
_INPROCESS_RELAY_HOST: str = "127.0.0.1"
_INPROCESS_RELAY_PORT: int = 8829
_EXTERNAL_RELAY_URL: Optional[str] = os.environ.get("LUCIFER_RELAY_URL") or None


def _is_port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    connect_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    try:
        with socket.create_connection((connect_host, port), timeout=timeout):
            return True
    except OSError:
        return False


def configure_external_relay_url(url: Optional[str]) -> None:
    global _EXTERNAL_RELAY_URL
    _EXTERNAL_RELAY_URL = url.rstrip("/") if url else None


def _should_use_external_relay() -> bool:
    if not _EXTERNAL_RELAY_URL:
        return False
    return len(fleet_manager.list_bots()) == 0


def ensure_relay_started(host: str = "127.0.0.1", port: int = 8829) -> Dict[str, Any]:
    """
    Ensures a Lucifer RelayServer is reachable on host:port.
    - If port is free, starts RelayServer in a background daemon thread.
    - If port is already bound by an external process (e.g. start.py or web/server.py),
      configures transparent HTTP forwarding to that relay instead of failing.
    """
    global _INPROCESS_RELAY_SERVER, _INPROCESS_RELAY_HOST, _INPROCESS_RELAY_PORT, _EXTERNAL_RELAY_URL

    with _RELAY_LOCK:
        _INPROCESS_RELAY_HOST = host
        _INPROCESS_RELAY_PORT = port
        local_url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"

        if _INPROCESS_RELAY_SERVER is not None:
            return {"mode": "in_process", "url": local_url, "host": host, "port": port}

        if _is_port_open(host, port):
            _EXTERNAL_RELAY_URL = local_url
            print(
                f"[MCP] Detected existing RelayServer at {local_url}; using external HTTP relay mode.",
                file=sys.stderr,
            )
            return {"mode": "external_http_proxy", "url": local_url, "host": host, "port": port}

        ready_evt = threading.Event()
        startup_error: Dict[str, Optional[BaseException]] = {"err": None}

        def _run_relay_loop():
            global _INPROCESS_RELAY_SERVER
            try:
                from core.relay_server import RelayServer

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                srv = RelayServer(host=host, port=port)
                loop.run_until_complete(srv.start())
                _INPROCESS_RELAY_SERVER = srv
                ready_evt.set()
                loop.run_forever()
            except BaseException as exc:
                startup_error["err"] = exc
                ready_evt.set()

        t = threading.Thread(target=_run_relay_loop, name="LuciferMCPRelay", daemon=True)
        t.start()
        ready_evt.wait(timeout=4.0)

        if startup_error["err"] is not None:
            if _is_port_open(host, port):
                _EXTERNAL_RELAY_URL = local_url
                return {"mode": "external_http_proxy", "url": local_url, "host": host, "port": port}
            return {
                "mode": "error",
                "url": local_url,
                "error": str(startup_error["err"]),
            }

        return {"mode": "in_process", "url": local_url, "host": host, "port": port}


def _http_json_sync(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    base = (_EXTERNAL_RELAY_URL or f"http://127.0.0.1:{_INPROCESS_RELAY_PORT}").rstrip("/")
    url = f"{base}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}: {raw}"}
    except Exception as e:
        return {"ok": False, "error": f"Relay HTTP request failed: {e}"}


async def _http_json_async(method: str, path: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 12.0) -> Dict[str, Any]:
    base = (_EXTERNAL_RELAY_URL or f"http://127.0.0.1:{_INPROCESS_RELAY_PORT}").rstrip("/")
    url = f"{base}{path}"
    client_timeout = aiohttp.ClientTimeout(total=timeout + 2.0)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.request(method.upper(), url, json=payload) as resp:
                text = await resp.text()
                try:
                    return json.loads(text)
                except Exception:
                    return {"ok": False, "error": f"HTTP {resp.status}: {text}"}
    except Exception as e:
        return {"ok": False, "error": f"Relay async HTTP request failed: {e}"}


# ---------------------------------------------------------------------------
# Shared Resolution & Dispatch Helpers
# ---------------------------------------------------------------------------
def _resolve_item_id(item_id_or_name: Any) -> Optional[int]:
    s = str(item_id_or_name or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    iid = get_item_id(s)
    if iid is not None:
        return iid
    matches = search_items(s, limit=5)
    for m in matches:
        if str(m.get("name", "")).strip().lower() == s.lower():
            return int(m["id"])
    return None


def _resolve_target_bot(bot_name: str = "first") -> Optional[str]:
    clean = str(bot_name or "first").strip()
    if clean.lower() in ("all", "global"):
        return clean
    if clean.lower() == "first":
        bots = fleet_manager.list_bots()
        if not bots:
            return None
        online = [b for b in bots if b.is_alive or b.status == "online"]
        return (online or bots)[0].name
    bot = fleet_manager.get_bot(clean)
    return bot.name if bot else clean


def _queue_bridge_cmd(bot_name: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    safe_params = params if isinstance(params, dict) else {}
    if _should_use_external_relay():
        res = _http_json_sync(
            "POST",
            "/api/command",
            {"bot": bot_name, "action": action, "params": safe_params},
        )
        return str(res.get("command_id") or res.get("targeted_bots") or "external")

    target = _resolve_target_bot(bot_name)
    if target is None and str(bot_name).strip().lower() == "first":
        return ""
    return fleet_manager.queue_command(
        bot_name=target if target is not None else bot_name,
        action=action,
        params=safe_params,
    )


async def _exec_bridge_sync(
    bot_name: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 12.0,
) -> Dict[str, Any]:
    safe_params = params if isinstance(params, dict) else {}
    if _should_use_external_relay():
        return await _http_json_async(
            "POST",
            "/api/execute",
            {
                "bot": bot_name,
                "action": action,
                "params": safe_params,
                "timeout": timeout,
            },
            timeout=timeout,
        )

    target = _resolve_target_bot(bot_name)
    if target is None:
        return {"ok": False, "error": "No bots connected to relay."}

    return await fleet_manager.aexecute_and_wait(
        bot_name=target,
        action=action,
        params=safe_params,
        timeout=timeout,
    )


def _load_server_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    ex = PROJECT_ROOT / "config.example.json"
    if ex.exists():
        try:
            return json.loads(ex.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"server": {"host": "127.0.0.1", "mcp_port": 8828, "relay_port": 8829}}


# ===========================================================================
# Existing Core & Fleet Tools (30 preserved tools)
# ===========================================================================

@mcp.tool()
def luci_fleet_status() -> Dict[str, Any]:
    """Returns a high-level summary of the connected Lucifer bot fleet, online counts, captchas, and HTTP blocks."""
    if _should_use_external_relay():
        return _http_json_sync("GET", "/api/status")
    return fleet_manager.get_fleet_summary()


@mcp.tool()
def luci_bot_list() -> List[Dict[str, Any]]:
    """Lists all bots with their status, current world, coordinates, gems, level, and ping."""
    if _should_use_external_relay():
        summary = _http_json_sync("GET", "/api/status")
        bots_list = summary.get("bots")
        return bots_list if isinstance(bots_list, list) else []

    bots = fleet_manager.list_bots()
    return [
        {
            "name": b.name,
            "status": b.status,
            "raw_status": b.raw_status,
            "google_status": b.google_status,
            "captcha_status": b.captcha_status,
            "world": b.world,
            "position": {"x": b.x, "y": b.y},
            "gems": b.gem_count,
            "pearls": b.pearl_count,
            "level": b.level,
            "ping": b.ping,
            "is_alive": b.is_alive,
            "is_http_blocked": b.is_http_blocked,
            "automations": b.automations,
        }
        for b in bots
    ]


@mcp.tool()
def luci_bot_inventory(bot_name: str) -> Dict[str, Any]:
    """Returns the inventory of a specific bot with item names and quantities."""
    if _should_use_external_relay():
        return _http_json_sync("GET", f"/api/bot/{bot_name}/inventory")

    target = _resolve_target_bot(bot_name)
    bot = fleet_manager.get_bot(target) if target else None
    if not bot:
        return {"error": f"Bot '{bot_name}' not found."}

    items_with_names = []
    for it in bot.inventory:
        iid = it.get("id", 0)
        items_with_names.append({
            "id": iid,
            "name": get_item_name(iid),
            "count": it.get("count", 0),
            "isActive": it.get("isActive", False),
        })

    return {
        "bot": bot.name,
        "item_count": len(items_with_names),
        "items": items_with_names,
    }


@mcp.tool()
def luci_warp(world: str, door_id: str = "", bot_name: str = "all") -> str:
    """Warps a bot or all bots to a target world with an optional door ID."""
    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="warp",
        params={"world": world.upper(), "id": door_id},
    )
    target = "all bots" if bot_name.lower() in ("all", "global") else f"bot '{bot_name}'"
    return f"Warp command queued for {target} -> {world.upper()}:{door_id} (cmd_id: {cmd_id})"


@mcp.tool()
def luci_say(text: str, bot_name: str = "all") -> str:
    """Makes a bot or all bots say a message in chat. Pure ASCII only!"""
    clean_text = sanitize_lua_ascii(text)
    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="say",
        params={"text": clean_text},
    )
    return f"Say command queued (cmd_id: {cmd_id})"


@mcp.tool()
def luci_find_path(x: int, y: int, bot_name: str) -> str:
    """Finds path and moves a bot to specific tile coordinates (x, y)."""
    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="find_path",
        params={"x": x, "y": y},
    )
    return f"Pathfind command queued for '{bot_name}' -> ({x}, {y}) (cmd_id: {cmd_id})"


@mcp.tool()
def luci_place_block(x: int, y: int, item_id_or_name: str, bot_name: str) -> str:
    """Places a block or seed at tile (x, y). Resolves item name to ID automatically."""
    iid = _resolve_item_id(item_id_or_name)
    if iid is None:
        return f"Error: Could not find item ID for '{item_id_or_name}'."

    _queue_bridge_cmd(
        bot_name=bot_name,
        action="place",
        params={"x": x, "y": y, "item_id": iid},
    )
    return f"Place block command queued for '{bot_name}' (ID {iid}: {get_item_name(iid)}) at ({x}, {y})"


@mcp.tool()
def luci_punch_tile(x: int, y: int, bot_name: str) -> str:
    """Punches/breaks a tile at coordinates (x, y)."""
    _queue_bridge_cmd(
        bot_name=bot_name,
        action="hit",
        params={"x": x, "y": y},
    )
    return f"Punch command queued for '{bot_name}' at ({x}, {y})"


@mcp.tool()
def luci_collect(range_tiles: int = 2, interval_ms: int = 150, bot_name: str = "all") -> str:
    """Collects floating items and gems within range."""
    _queue_bridge_cmd(
        bot_name=bot_name,
        action="collect",
        params={"range": range_tiles, "interval": interval_ms},
    )
    return f"Collect command queued (range: {range_tiles}, interval: {interval_ms}ms)"


@mcp.tool()
def luci_drop_item(item_id_or_name: str, count: int = 1, fast: bool = False, bot_name: str = "all") -> str:
    """Drops an item from inventory."""
    iid = _resolve_item_id(item_id_or_name)
    if iid is None:
        return f"Error: Could not resolve item ID for '{item_id_or_name}'."

    _queue_bridge_cmd(
        bot_name=bot_name,
        action="drop",
        params={"item_id": iid, "count": count, "fast": fast},
    )
    return f"Drop command queued for {count}x {get_item_name(iid)} (ID: {iid})"


@mcp.tool()
def luci_trash_item(item_id_or_name: str, count: int = 1, fast: bool = False, bot_name: str = "all") -> str:
    """Trashes an item from inventory."""
    iid = _resolve_item_id(item_id_or_name)
    if iid is None:
        return f"Error: Could not resolve item ID for '{item_id_or_name}'."

    _queue_bridge_cmd(
        bot_name=bot_name,
        action="trash",
        params={"item_id": iid, "count": count, "fast": fast},
    )
    return f"Trash command queued for {count}x {get_item_name(iid)} (ID: {iid})"


@mcp.tool()
def luci_set_automation(automation_name: str, enabled: bool, bot_name: str = "all") -> str:
    """
    Toggles a native Lucifer automation.
    Available: 'auto_farm', 'auto_geiger', 'auto_spam', 'auto_fish', 'auto_collect',
    'auto_trash', 'rotation', 'auto_cook', 'auto_transfer', 'auto_harvest',
    'auto_plant', 'auto_break', 'auto_place', 'auto_clear'.
    """
    valid = (
        "auto_farm",
        "auto_geiger",
        "auto_spam",
        "auto_fish",
        "auto_collect",
        "auto_trash",
        "rotation",
        "auto_cook",
        "auto_transfer",
        "auto_harvest",
        "auto_plant",
        "auto_break",
        "auto_place",
        "auto_clear",
    )
    if automation_name not in valid:
        return f"Error: Invalid automation '{automation_name}'. Supported: {', '.join(valid)}"

    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="set_automation",
        params={"automation": automation_name, "enabled": enabled},
    )
    state_str = "ENABLED" if enabled else "DISABLED"
    return f"Automation '{automation_name}' {state_str} for {bot_name} (cmd_id: {cmd_id})"


@mcp.tool()
def luci_run_script(
    lua_code: str,
    bot_name: str = "all",
    use_thread: bool = False,
    use_bot_runner: bool = False,
    auto_sanitize_ascii: bool = True,
) -> str:
    """
    Queues arbitrary Lua code on a target bot or all bots.
    For synchronous execution with print()/return output and error traceback,
    prefer luci_eval_sync instead.
    """
    final_code = sanitize_lua_ascii(lua_code) if auto_sanitize_ascii else lua_code
    params: Dict[str, Any] = {"code": final_code}
    if use_thread:
        params["use_thread"] = True
    if use_bot_runner:
        params["use_bot_runner"] = True

    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="run_script",
        params=params,
    )
    return f"Custom Lua script dispatched to {bot_name} (cmd_id: {cmd_id})"


@mcp.tool()
def luci_search_item(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Searches Growtopia item database for IDs, seed pairs, and names."""
    return search_items(query, limit)


@mcp.tool()
def luci_glserver_info() -> Dict[str, Any]:
    """Returns glServer (Google Login Server) connection string and configuration."""
    return {
        "host": glserver_client.host,
        "port": glserver_client.port,
        "access_key": glserver_client.access_key,
        "lucifer_connection_string": glserver_client.connection_string,
        "usage": "Copy lucifer_connection_string and paste into Lucifer Gmaillog settings, then press Connect.",
    }


@mcp.tool()
def luci_glserver_set(connection_string: str) -> Dict[str, Any]:
    """
    Updates the glServer connection string dynamically.
    Format: 'localhost:4580:<access_key>' or '<host>:<port>:<key>'.
    """
    return glserver_client.set_connection_string(connection_string)


@mcp.tool()
def luci_bot_google_status(bot_name: str) -> Dict[str, Any]:
    """Diagnoses Google OAuth login status for a specific bot."""
    if _should_use_external_relay():
        summary = _http_json_sync("GET", "/api/status")
        for b in summary.get("bots") or []:
            if str(b.get("name", "")).lower() == bot_name.strip().lower():
                gs = int(b.get("google_status") or 0)
                return {
                    "bot": b.get("name"),
                    "google_status": gs,
                    "diagnosis": describe_google_status(gs),
                }
        return {"error": f"Bot '{bot_name}' not found."}

    bot = fleet_manager.get_bot(bot_name)
    if not bot:
        return {"error": f"Bot '{bot_name}' not found."}
    return {
        "bot": bot_name,
        "google_status": bot.google_status,
        "diagnosis": bot.google_diagnosis,
    }


@mcp.tool()
def luci_diagnose_status(status_id: int) -> Dict[str, Any]:
    """Explains a numerical BotStatus or GoogleStatus code and offers solutions."""
    return {
        "code": status_id,
        "bot_status_meaning": describe_bot_status(status_id),
        "google_status_meaning": describe_google_status(status_id),
    }


@mcp.tool()
def luci_glserver_captcha_guide() -> Dict[str, Any]:
    """Returns the complete step-by-step guide on how to configure Google login captcha solving in glServer."""
    return glserver_client.get_captcha_guide()


@mcp.tool()
def luci_glserver_parse_response(response_text: str) -> Dict[str, Any]:
    """Parses raw HTTP Response logs from Lucifer / glServer (e.g. statusCode 13 Couldn't Solve Captcha) and returns exact solutions."""
    return glserver_client.parse_http_response(response_text)


@mcp.tool()
def luci_render_world_map(bot_name: str = "all") -> Dict[str, Any]:
    """
    Renders an authentic 1:1 pixel-perfect minimap PNG image of the world(s)
    matching Lucifer's native [Map] tab GUI (showing 100x60 tiles, lava, rocks, and bot position).
    Returns saved PNG file paths and world details for all specified bots.
    """
    from core.minimap_renderer import render_minimap

    bots = fleet_manager.list_bots() if bot_name.lower() in ("all", "global") else [fleet_manager.get_bot(bot_name)]
    bots = [b for b in bots if b]
    if not bots:
        return {"error": f"No active bots found matching '{bot_name}'."}

    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "maps")
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for b in bots:
        w_name = b.world or "UNKNOWN"
        img = render_minimap(bot_x=b.x, bot_y=b.y, world_name=w_name, is_public=True)
        img_path = os.path.join(output_dir, f"{b.name}_{w_name}_map.png")
        img.save(img_path, format="PNG")
        results.append({
            "bot": b.name,
            "world": w_name,
            "position": {"x": b.x, "y": b.y},
            "map_image_path": img_path,
        })

    return {"count": len(results), "maps": results}


@mcp.tool()
def luci_set_setting(setting_name: str, value: Any, bot_name: str = "all") -> str:
    """
    Toggles or updates any Lucifer bot setting or subsystem configuration directly.
    Supports Safety, Inventory & Delays, Farm, Rotation, and Spam settings.
    """
    val = value
    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes", "on", "aktif"):
            val = True
        elif value.lower() in ("false", "0", "no", "off", "kapali"):
            val = False
        elif value.isdigit():
            val = int(value)

    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="set_setting",
        params={"setting": setting_name, "value": val},
    )
    return f"Setting '{setting_name}' = {val} dispatched to {bot_name} (cmd_id: {cmd_id})"


@mcp.tool()
def luci_fleet_census(item_query: Optional[str] = None) -> Dict[str, Any]:
    """
    Scans the inventories of all connected bots across the entire fleet.
    Aggregates total quantities of all items (e.g. Sugar Cane, Pepper, World Locks, Gems, Seeds).
    Optionally filters by item name or ID.
    """
    if _should_use_external_relay():
        summary = _http_json_sync("GET", "/api/status")
        bots_meta = summary.get("bots") or []
        if not bots_meta:
            return {"error": "No active bots connected."}
        aggregate: Dict[int, Dict[str, Any]] = {}
        total_gems = sum(int(b.get("gems") or 0) for b in bots_meta)
        total_pearls = sum(int(b.get("pearls") or 0) for b in bots_meta)
        for b in bots_meta:
            bname = b.get("name", "")
            inv_res = _http_json_sync("GET", f"/api/bot/{bname}/inventory")
            for it in inv_res.get("items") or []:
                iid = int(it.get("id", 0))
                cnt = int(it.get("count", 0))
                if iid not in aggregate:
                    aggregate[iid] = {
                        "id": iid,
                        "name": it.get("name") or get_item_name(iid),
                        "total_count": 0,
                        "bots_holding": [],
                    }
                aggregate[iid]["total_count"] += cnt
                aggregate[iid]["bots_holding"].append({"bot": bname, "count": cnt})
        items_list = list(aggregate.values())
        if item_query:
            q = item_query.lower().strip()
            items_list = [
                it for it in items_list
                if q in it["name"].lower() or (q.isdigit() and int(q) == it["id"])
            ]
        items_list.sort(key=lambda x: x["total_count"], reverse=True)
        return {
            "bot_count": len(bots_meta),
            "fleet_total_gems": total_gems,
            "fleet_total_pearls": total_pearls,
            "distinct_items": len(items_list),
            "items": items_list[:50],
        }

    bots = fleet_manager.list_bots()
    if not bots:
        return {"error": "No active bots connected."}

    aggregate: Dict[int, Dict[str, Any]] = {}
    total_gems = sum(b.gem_count for b in bots)
    total_pearls = sum(b.pearl_count for b in bots)

    for b in bots:
        for it in b.inventory:
            iid = it.get("id", 0)
            cnt = it.get("count", 0)
            if iid not in aggregate:
                aggregate[iid] = {
                    "id": iid,
                    "name": get_item_name(iid),
                    "total_count": 0,
                    "bots_holding": [],
                }
            aggregate[iid]["total_count"] += cnt
            aggregate[iid]["bots_holding"].append({"bot": b.name, "count": cnt})

    items_list = list(aggregate.values())
    if item_query:
        q = item_query.lower().strip()
        items_list = [
            it for it in items_list
            if q in it["name"].lower() or (q.isdigit() and int(q) == it["id"])
        ]

    items_list.sort(key=lambda x: x["total_count"], reverse=True)

    return {
        "bot_count": len(bots),
        "fleet_total_gems": total_gems,
        "fleet_total_pearls": total_pearls,
        "distinct_items": len(items_list),
        "items": items_list[:50],
    }


@mcp.tool()
async def luci_auto_test(lua_code: str, bot_name: str = "first", wait_seconds: float = 2.5) -> Dict[str, Any]:
    """
    Executes a Lua script on Lucifer, reads live console logs from the [Logs] tab,
    detects any runtime errors, automatically diagnoses and patches the script with EVREN AI,
    and saves learned bug patterns to memory.
    """
    from core.auto_tester import auto_tester
    return await auto_tester.execute_and_verify(lua_code=lua_code, bot_name=bot_name, wait_seconds=wait_seconds)


@mcp.tool()
def luci_get_bot_logs(bot_name: str = "first", max_chars: int = 1500) -> Dict[str, Any]:
    """
    Returns the cached packet, console, and script error logs from Lucifer's [Logs] tab for a bot.
    For an on-demand live fetch directly from the bridge, use luci_get_console_and_logs.
    """
    if _should_use_external_relay():
        target = "first" if bot_name.lower() in ("first", "all") else bot_name
        if target == "first":
            status_res = _http_json_sync("GET", "/api/status")
            bots_list = status_res.get("bots") or []
            if not bots_list:
                return {"error": f"Bot '{bot_name}' not found."}
            target = bots_list[0].get("name", "")
        res = _http_json_sync("GET", f"/api/bot/{target}/logs")
        raw = str(res.get("logs") or "")
        return {"bot": target, "logs": raw[-max_chars:] if raw else "No logs recorded yet."}

    bots = fleet_manager.list_bots()
    b = bots[0] if (bot_name.lower() in ("first", "all") and bots) else fleet_manager.get_bot(bot_name)
    if not b:
        return {"error": f"Bot '{bot_name}' not found."}

    logs = b.logs or b.raw_info.get("logs", "")
    return {
        "bot": b.name,
        "world": b.world,
        "logs": logs[-max_chars:] if logs else "No logs recorded yet.",
    }


@mcp.tool()
def luci_proxy_next(bot_name: str = "all") -> str:
    """
    Instructs Lucifer to switch to the next proxy in ProxyManager.
    Crucial for bypassing Status 13 (HTTP Block) or IP restrictions.
    """
    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="switch_proxy",
        params={},
    )
    return f"Proxy switch command queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_setup_farm(world: str, item_id_or_name: str, mag_x: int = -1, mag_y: int = -1, bot_name: str = "all") -> str:
    """
    Automates setting up Lucifer's built-in Auto Farm engine for a specific world,
    Magplant coordinate, and item ID.
    """
    iid = _resolve_item_id(item_id_or_name)
    if iid is None:
        return f"Error: Could not resolve item ID for '{item_id_or_name}'."

    _queue_bridge_cmd(bot_name, "warp", {"world": world.upper()})
    _queue_bridge_cmd(bot_name, "set_setting", {"setting": "id", "value": iid})
    _queue_bridge_cmd(bot_name, "set_setting", {"setting": "auto_break", "value": True})
    _queue_bridge_cmd(bot_name, "set_setting", {"setting": "auto_place", "value": True})
    if mag_x >= 0 and mag_y >= 0:
        _queue_bridge_cmd(bot_name, "set_setting", {"setting": "mag_x", "value": mag_x})
        _queue_bridge_cmd(bot_name, "set_setting", {"setting": "mag_y", "value": mag_y})
        _queue_bridge_cmd(bot_name, "set_setting", {"setting": "auto_remote", "value": True})
    _queue_bridge_cmd(bot_name, "set_automation", {"automation": "auto_farm", "enabled": True})

    return f"Auto Farm configured for world {world.upper()}, Item {get_item_name(iid)} (ID: {iid}), Mag: ({mag_x}, {mag_y})"


@mcp.tool()
def luci_analyze_risk(action_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates risks, ban hazards (http_block 13, location_banned 5, autoban),
    proxy density, and login methods before executing sensitive operations.
    Action types: 'login', 'delay', 'mass_warp'.
    """
    from core.safety_advisor import safety_advisor

    act = action_type.lower().strip()
    if act == "login":
        accounts = details.get("accounts", [])
        proxy_count = details.get("proxy_count", 0)
        return safety_advisor.evaluate_login_request(accounts=accounts, proxy_count=proxy_count)
    elif act in ("delay", "speed"):
        delay = details.get("delay_ms", 180)
        sub_act = details.get("action", "hit")
        return safety_advisor.evaluate_delay_safety(delay_ms=delay, action=sub_act)
    elif act in ("mass_warp", "warp"):
        cnt = details.get("bot_count", 1)
        w = details.get("world", "")
        return safety_advisor.evaluate_mass_warp(bot_count=cnt, target_world=w)
    return {"risk_level": "LOW", "note": f"Action '{action_type}' has no critical automated ban risks identified."}


def _parse_proxy_string(proxy_str: str) -> Dict[str, Any]:
    parts = proxy_str.strip().split(":")
    if len(parts) >= 4:
        return {"ip": parts[0], "port": int(parts[1]), "username": parts[2], "password": parts[3]}
    elif len(parts) >= 2:
        return {"ip": parts[0], "port": int(parts[1]), "username": "", "password": ""}
    return {"ip": proxy_str, "port": 1080, "username": "", "password": ""}


@mcp.tool()
def luci_set_bot_proxy(bot_names: List[str], proxy_string: str) -> Dict[str, Any]:
    """
    Assigns or updates a proxy to SPECIFIC selected bots ONLY (leaving all other bots untouched).
    Accepts format: 'ip:port:user:pass' or 'ip:port'.
    """
    parsed = _parse_proxy_string(proxy_string)
    dispatched = []
    for name in bot_names:
        cmd_id = _queue_bridge_cmd(name, "set_proxy", parsed)
        dispatched.append({"bot": name, "cmd_id": cmd_id})

    return {
        "success": True,
        "assigned_proxy": f"{parsed['ip']}:{parsed['port']}",
        "target_bots": bot_names,
        "dispatched_count": len(dispatched),
    }


@mcp.tool()
def luci_assign_proxies_bulk(bot_to_proxy_map: Dict[str, str]) -> Dict[str, Any]:
    """Assigns individual proxies to corresponding specific bots."""
    results = []
    for bot_name, proxy_str in bot_to_proxy_map.items():
        parsed = _parse_proxy_string(proxy_str)
        cmd_id = _queue_bridge_cmd(bot_name, "set_proxy", parsed)
        results.append({"bot": bot_name, "proxy": f"{parsed['ip']}:{parsed['port']}", "cmd_id": cmd_id})

    return {"assigned_count": len(results), "details": results}


# ===========================================================================
# Human-Equivalent Lucifer v2.88 p2 MCP Tools (Sync Execution, Logs, World,
# Tile, Lifecycle, Movement, Packets, Rotation, WorldManager, ProxyManager,
# Subsystems, Files, Item Details, and Docs)
# ===========================================================================

@mcp.tool()
async def luci_eval_sync(
    lua_code: str,
    bot_name: str = "first",
    timeout_seconds: float = 12.0,
    auto_sanitize_ascii: bool = True,
) -> Dict[str, Any]:
    """
    Executes arbitrary Lua code synchronously inside Lucifer and waits for the live
    result, captured print() output, or Lua syntax/runtime traceback.
    Gives AI assistants exact human-in-the-Executor feedback.
    """
    code = sanitize_lua_ascii(lua_code) if auto_sanitize_ascii else lua_code
    return await _exec_bridge_sync(
        bot_name=bot_name,
        action="eval_sync",
        params={"code": code},
        timeout=timeout_seconds,
    )


@mcp.tool()
def luci_stop_script(bot_name: str = "all") -> str:
    """Stops the currently running Lua script inside Lucifer on the target bot(s)."""
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="stop_script", params={})
    return f"stop_script command queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
async def luci_get_console_and_logs(
    bot_name: str = "first",
    clear_after: bool = False,
    max_chars: int = 4000,
    live_fetch: bool = True,
) -> Dict[str, Any]:
    """
    Fetches live Console output (bot:getConsole().contents) and [Logs] tab history
    (bot:getLog().content) directly from Lucifer, optionally clearing console afterwards.
    Falls back to cached telemetry if live fetch times out.
    """
    if live_fetch:
        res = await _exec_bridge_sync(
            bot_name=bot_name,
            action="get_console_logs",
            params={"clear": clear_after},
            timeout=8.0,
        )
        if res.get("ok") and isinstance(res.get("result"), dict):
            payload = res["result"]
            bot_log = str(payload.get("bot_log") or "")
            console_txt = str(payload.get("console") or "")
            return {
                "ok": True,
                "live": True,
                "bot": res.get("bot") or bot_name,
                "bot_log": bot_log[-max_chars:] if max_chars > 0 else bot_log,
                "console": console_txt[-max_chars:] if max_chars > 0 else console_txt,
                "cleared": clear_after,
            }

    cached = luci_get_bot_logs(bot_name=bot_name, max_chars=max_chars)
    return {
        "ok": "error" not in cached,
        "live": False,
        "bot": cached.get("bot", bot_name),
        "world": cached.get("world", ""),
        "bot_log": cached.get("logs", ""),
        "console": "",
    }


@mcp.tool()
def luci_code_analyze(lua_code: str) -> Dict[str, Any]:
    """
    Analyzes Lucifer Lua code BEFORE execution for:
    - 7-bit ASCII violations (which crash or corrupt Growtopia fonts),
    - Common non-existent or hallucinated API calls vs Lucifer v2.88 p2,
    - Dangerous low sleep() delays or tight loops without sleep() (autoban risk).
    """
    ascii_ok, violations = validate_lua_ascii(lua_code)
    warnings: List[str] = []
    ban_risks: List[str] = []

    hallucinated_patterns = [
        (r"\bbot:collectItems\s*\(", "Use bot:collect(range, interval) instead of bot:collectItems()."),
        (r"\baddHook\s*\(\s*['\"]onVariant['\"]", "Verify Lucifer hook event name is VariantList / packet hook rather than 'onVariant'."),
        (r"\bgetTile\s*\(\s*\d+\s*,\s*\d+\s*\)", "Prefer bot:getWorld():getTile(x, y) (or getWorld():getTile(x, y)) when using Bot instance methods."),
    ]
    for pattern, advice in hallucinated_patterns:
        if re.search(pattern, lua_code):
            warnings.append(advice)

    # Check suspiciously low sleep durations
    for match in re.finditer(r"\bsleep\s*\(\s*(\d+)\s*\)", lua_code):
        ms = int(match.group(1))
        if ms < 100 and ("hit(" in lua_code or "place(" in lua_code or "warp(" in lua_code):
            ban_risks.append(f"Low sleep({ms}) alongside hit/place/warp may trigger Growtopia server autoban (>=160ms recommended for hit).")

    if re.search(r"\bwhile\s+true\s+do\b", lua_code) and "sleep(" not in lua_code:
        warnings.append("Infinite 'while true do' loop detected without sleep(...), which will freeze Lucifer UI.")

    sanitized = sanitize_lua_ascii(lua_code)
    return {
        "ok_for_lucifer": ascii_ok and len(warnings) == 0 and len(ban_risks) == 0,
        "ascii_valid": ascii_ok,
        "ascii_violations": violations[:20],
        "warnings": warnings,
        "ban_risks": ban_risks,
        "sanitized_preview": sanitized if not ascii_ok else lua_code,
    }


@mcp.tool()
async def luci_add_bot(
    name: str,
    password: str = "",
    recovery: str = "",
    login_type: str = "growid",
    executor_bot: str = "first",
) -> Dict[str, Any]:
    """
    Adds a new Growtopia account/bot inside Lucifer dynamically.
    login_type: 'growid', 'ubi', 'steam', or 'token'.
    """
    lt = login_type.strip().lower()
    if lt not in ("growid", "ubi", "steam", "token"):
        return {"ok": False, "error": f"Invalid login_type '{login_type}'. Use growid, ubi, steam, or token."}
    return await _exec_bridge_sync(
        bot_name=executor_bot,
        action="add_bot",
        params={"name": name, "password": password, "recovery": recovery, "login_type": lt},
        timeout=10.0,
    )


@mcp.tool()
async def luci_remove_bot(target_bot_name: str, executor_bot: str = "first") -> Dict[str, Any]:
    """Removes a bot from Lucifer's bot list via removeBot(name)."""
    return await _exec_bridge_sync(
        bot_name=executor_bot,
        action="remove_bot",
        params={"target_bot": target_bot_name, "name": target_bot_name},
        timeout=10.0,
    )


@mcp.tool()
def luci_connect_bot(bot_name: str = "all") -> str:
    """Connects the target bot(s) to Growtopia servers (bot:connect())."""
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="connect", params={})
    return f"Connect command queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_disconnect_bot(bot_name: str = "all") -> str:
    """Disconnects the target bot(s) from Growtopia servers (bot:disconnect())."""
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="disconnect", params={})
    return f"Disconnect command queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
async def luci_update_bot_identity(
    bot_name: str,
    country: str = "",
    mac: str = "",
    rid: str = "",
    skin: Optional[int] = None,
    platform: str = "",
    bubble: str = "",
) -> Dict[str, Any]:
    """Updates bot identity/spoof fields (country, mac, rid, skin color int, platform, chat bubble)."""
    params: Dict[str, Any] = {}
    if country:
        params["country"] = country
    if mac:
        params["mac"] = mac
    if rid:
        params["rid"] = rid
    if skin is not None:
        params["skin"] = skin
    if platform:
        params["platform"] = platform
    if bubble:
        params["bubble"] = bubble
    if not params:
        return {"ok": False, "error": "Provide at least one identity field to update."}
    return await _exec_bridge_sync(bot_name=bot_name, action="update_identity", params=params, timeout=10.0)


@mcp.tool()
def luci_move(
    bot_name: str,
    direction: str = "",
    steps: int = 1,
    tile_x: Optional[int] = None,
    tile_y: Optional[int] = None,
    dx: Optional[int] = None,
    dy: Optional[int] = None,
    face_left: Optional[bool] = None,
) -> str:
    """
    Moves a bot manually using Lucifer movement primitives:
    - direction in ('left', 'right', 'up', 'down') with steps (bot:moveLeft/Right/Up/Down)
    - OR tile_x & tile_y (bot:moveTile)
    - OR relative dx & dy (bot:moveTo)
    Optionally sets facing direction (face_left=True/False).
    """
    params: Dict[str, Any] = {"range": steps}
    if direction:
        params["mode"] = direction.strip().lower()
    if tile_x is not None and tile_y is not None:
        if not direction:
            params["mode"] = "tile"
        params["x"] = tile_x
        params["y"] = tile_y
    if dx is not None:
        params["dx"] = dx
    if dy is not None:
        params["dy"] = dy
    if face_left is not None:
        params["face_left"] = face_left
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="move", params=params)
    return f"Move command queued for '{bot_name}' ({params}) (cmd_id: {cmd_id})"


@mcp.tool()
async def luci_find_world_path(
    x: int,
    y: int,
    bot_name: str = "first",
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    """Queries Lucifer's A* pathfinder (bot:findWorldPath(x, y)) to check reachability and path."""
    return await _exec_bridge_sync(
        bot_name=bot_name,
        action="find_world_path",
        params={"x": x, "y": y},
        timeout=timeout_seconds,
    )


@mcp.tool()
def luci_enter_door(password: str = "", bot_name: str = "all") -> str:
    """Enters the door/portal at the bot's current tile, optionally supplying a door password."""
    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="enter_door",
        params={"password": password},
    )
    return f"Enter door queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_leave_world(bot_name: str = "all") -> str:
    """Leaves the current world back to the EXIT/menu screen (bot:leaveWorld())."""
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="leave", params={})
    return f"Leave world queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_respawn(bot_name: str = "all") -> str:
    """Respawns the bot at the white door in the current world (bot:respawn())."""
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="respawn", params={})
    return f"Respawn queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_wrench(
    x: Optional[int] = None,
    y: Optional[int] = None,
    netid: Optional[int] = None,
    bot_name: str = "first",
) -> str:
    """Wrenches a tile at (x, y) or a player by netid (bot:wrench / bot:wrenchPlayer)."""
    params: Dict[str, Any] = {}
    if netid is not None:
        params["netid"] = netid
    if x is not None:
        params["x"] = x
    if y is not None:
        params["y"] = y
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="wrench", params=params)
    return f"Wrench command queued for '{bot_name}' ({params}) (cmd_id: {cmd_id})"


@mcp.tool()
def luci_activate_tile(x: int, y: int, bot_name: str = "first") -> str:
    """Activates/interacts with a tile (sign, gate, entrance, vend, provider) at (x, y)."""
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="activate", params={"x": x, "y": y})
    return f"Activate tile ({x}, {y}) queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_equipment(action: str, item_id_or_name: str, bot_name: str = "all") -> str:
    """
    Equips, unequips, or uses an item from inventory.
    action: 'wear', 'unwear', or 'use'.
    """
    act = action.strip().lower()
    if act not in ("wear", "unwear", "use"):
        return f"Error: Invalid equipment action '{action}'. Use 'wear', 'unwear', or 'use'."
    iid = _resolve_item_id(item_id_or_name)
    if iid is None:
        return f"Error: Could not resolve item '{item_id_or_name}'."
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action=act, params={"item_id": iid})
    return f"{act} queued for {get_item_name(iid)} (ID: {iid}) on '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_buy(pack_or_item_name: str, bot_name: str = "all") -> str:
    """Buys a store pack/item from the Growtopia Store using bot:buy(name)."""
    clean_pack = sanitize_lua_ascii(pack_or_item_name)
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="buy", params={"pack": clean_pack})
    return f"Store buy('{clean_pack}') queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_retrieve(x: int, y: int, count: Optional[int] = None, bot_name: str = "first") -> str:
    """Retrieves items from a Magplant or Tesseract at tile (x, y)."""
    params: Dict[str, Any] = {"x": x, "y": y}
    if count is not None:
        params["count"] = count
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="retrieve", params=params)
    return f"Retrieve queued at ({x}, {y}) for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_send_packet(packet_type: int, packet_text: str, bot_name: str = "first") -> str:
    """Sends a text/action packet via bot:sendPacket(packet_type, packet_text)."""
    clean_text = sanitize_lua_ascii(packet_text)
    cmd_id = _queue_bridge_cmd(
        bot_name=bot_name,
        action="send_packet",
        params={"packet_type": packet_type, "text": clean_text},
    )
    return f"sendPacket(type={packet_type}) queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
def luci_send_raw_packet(
    pkt_type: int = 0,
    int_data: Optional[int] = None,
    int_x: Optional[int] = None,
    int_y: Optional[int] = None,
    pos_x: Optional[float] = None,
    pos_y: Optional[float] = None,
    flags: Optional[int] = None,
    bot_name: str = "first",
) -> str:
    """Sends a GameUpdatePacket via bot:sendRaw(pkt)."""
    params: Dict[str, Any] = {"type": pkt_type}
    if int_data is not None:
        params["int_data"] = int_data
    if int_x is not None:
        params["int_x"] = int_x
    if int_y is not None:
        params["int_y"] = int_y
    if pos_x is not None:
        params["pos_x"] = pos_x
    if pos_y is not None:
        params["pos_y"] = pos_y
    if flags is not None:
        params["flags"] = flags
    cmd_id = _queue_bridge_cmd(bot_name=bot_name, action="send_raw", params=params)
    return f"sendRaw(type={pkt_type}) queued for '{bot_name}' (cmd_id: {cmd_id})"


@mcp.tool()
async def luci_inspect_world(
    bot_name: str = "first",
    filter_item_id_or_name: Optional[str] = None,
    timeout_seconds: float = 12.0,
) -> Dict[str, Any]:
    """
    Inspects the bot's live world in real time: players (name, netid, coords, is_mod),
    dropped objects (optionally filtered by item), and foreground tile counts enriched
    with Growtopia item names.
    """
    params: Dict[str, Any] = {}
    if filter_item_id_or_name:
        iid = _resolve_item_id(filter_item_id_or_name)
        if iid is None:
            return {"ok": False, "error": f"Could not resolve filter item '{filter_item_id_or_name}'."}
        params["filter_item_id"] = iid

    res = await _exec_bridge_sync(
        bot_name=bot_name,
        action="inspect_world",
        params=params,
        timeout=timeout_seconds,
    )
    if res.get("ok") and isinstance(res.get("result"), dict):
        world_data = dict(res["result"])
        for entry in world_data.get("tile_summary", []) or []:
            if isinstance(entry, dict) and "id" in entry:
                entry["name"] = get_item_name(int(entry["id"]))
        for obj in world_data.get("objects", []) or []:
            if isinstance(obj, dict) and "id" in obj:
                obj["name"] = get_item_name(int(obj["id"]))
        res["result"] = world_data
    return res


@mcp.tool()
async def luci_inspect_tile(
    x: int,
    y: int,
    bot_name: str = "first",
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    """
    Inspects a single tile at (x, y): foreground/background IDs & item names, flags,
    harvest readiness (canHarvest), and TileExtra details (sign text, vend price, lock owner, etc.).
    """
    res = await _exec_bridge_sync(
        bot_name=bot_name,
        action="inspect_tile",
        params={"x": x, "y": y},
        timeout=timeout_seconds,
    )
    if res.get("ok") and isinstance(res.get("result"), dict):
        tile_data = dict(res["result"])
        fg = int(tile_data.get("fg") or 0)
        bg = int(tile_data.get("bg") or 0)
        tile_data["fg_name"] = get_item_name(fg) if fg > 0 else "Empty"
        tile_data["bg_name"] = get_item_name(bg) if bg > 0 else "Empty"
        res["result"] = tile_data
    return res


@mcp.tool()
async def luci_world_count_item(
    item_id_or_name: str,
    bot_name: str = "first",
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    """
    Counts how many tiles (fg/bg), harvest-ready trees, and dropped stacks of a specific item
    exist in the bot's current world, returning sample coordinates.
    """
    iid = _resolve_item_id(item_id_or_name)
    if iid is None:
        return {"ok": False, "error": f"Could not resolve item '{item_id_or_name}'."}

    res = await _exec_bridge_sync(
        bot_name=bot_name,
        action="world_count_item",
        params={"item_id": iid},
        timeout=timeout_seconds,
    )
    if res.get("ok") and isinstance(res.get("result"), dict):
        res["result"]["item_name"] = get_item_name(iid)
    return res


@mcp.tool()
async def luci_configure_rotation(
    enabled: Optional[bool] = None,
    settings: Optional[Dict[str, Any]] = None,
    bot_name: str = "all",
) -> Dict[str, Any]:
    """
    Configures Lucifer's Rotation engine (enabled toggle and settings such as
    pnb_in_home, harvest_until_level, one_by_one, auto_fill, warp_interval, etc.).
    """
    params: Dict[str, Any] = {"subsystem": "rotation", "settings": settings or {}}
    if enabled is not None:
        params["enabled"] = enabled

    if bot_name.lower() in ("all", "global"):
        cid = _queue_bridge_cmd(bot_name=bot_name, action="configure_subsystem", params=params)
        return {"ok": True, "queued": True, "cmd_id": cid, "subsystem": "rotation", "params": params}

    return await _exec_bridge_sync(bot_name=bot_name, action="configure_subsystem", params=params, timeout=10.0)


@mcp.tool()
async def luci_world_manager(
    operation: str,
    world: str = "",
    item_id_or_name: str = "",
    storage_type: str = "seed",
    bot_name: str = "first",
) -> Dict[str, Any]:
    """
    Controls Lucifer's WorldManager (used by Rotation).
    operation: 'add_farm', 'remove_farm', 'add_storage', 'remove_storage',
               'select_all', 'unselect_all', 'select_farm', 'unselect_farm'.
    """
    valid_ops = (
        "add_farm",
        "remove_farm",
        "add_storage",
        "remove_storage",
        "select_all",
        "unselect_all",
        "select_farm",
        "unselect_farm",
    )
    op = operation.strip().lower()
    if op not in valid_ops:
        return {"ok": False, "error": f"Invalid operation '{operation}'. Supported: {', '.join(valid_ops)}"}

    iid = 0
    if item_id_or_name:
        resolved = _resolve_item_id(item_id_or_name)
        if resolved is None:
            return {"ok": False, "error": f"Could not resolve item '{item_id_or_name}'."}
        iid = resolved

    return await _exec_bridge_sync(
        bot_name=bot_name,
        action="world_manager",
        params={
            "op": op,
            "world": world.strip().upper(),
            "item_id": iid,
            "storage_type": storage_type.strip().lower(),
        },
        timeout=10.0,
    )


@mcp.tool()
async def luci_configure_subsystem(
    subsystem: str,
    enabled: Optional[bool] = None,
    settings: Optional[Dict[str, Any]] = None,
    bot_name: str = "all",
) -> Dict[str, Any]:
    """
    Configures any Lucifer subsystem dynamically ('auto_farm', 'rotation', 'auto_geiger',
    'auto_spam', 'auto_fish', 'auto_cook', 'auto_transfer', 'auto_harvest', 'auto_plant',
    'auto_clear', or 'bot' for root Bot settings like legit_mode/auto_reconnect).
    """
    params: Dict[str, Any] = {"subsystem": subsystem.strip(), "settings": settings or {}}
    if enabled is not None:
        params["enabled"] = enabled

    if bot_name.lower() in ("all", "global"):
        cid = _queue_bridge_cmd(bot_name=bot_name, action="configure_subsystem", params=params)
        return {"ok": True, "queued": True, "cmd_id": cid, "subsystem": subsystem, "params": params}

    return await _exec_bridge_sync(bot_name=bot_name, action="configure_subsystem", params=params, timeout=10.0)


@mcp.tool()
async def luci_proxy_manager(
    operation: str,
    proxy_str: str = "",
    ip: str = "",
    port: int = 0,
    limit: int = 1,
    settings: Optional[Dict[str, Any]] = None,
    bot_name: str = "first",
) -> Dict[str, Any]:
    """
    Controls Lucifer's ProxyManager ('add', 'remove', 'set_limit', or custom 'settings').
    """
    params: Dict[str, Any] = {
        "op": operation.strip().lower(),
        "proxy_str": proxy_str.strip(),
        "ip": ip.strip(),
        "port": port,
        "limit": limit,
        "settings": settings or {},
    }
    return await _exec_bridge_sync(bot_name=bot_name, action="proxy_manager", params=params, timeout=10.0)


@mcp.tool()
async def luci_trash_and_pack_manager(
    operation: str,
    items: Optional[List[int]] = None,
    pack_name: str = "",
    item_id: int = 0,
    bot_name: str = "first",
) -> Dict[str, Any]:
    """
    Manages Lucifer's global auto-trash list and store pack list.
    operation: 'set_trash_list', 'get_trash_list', 'add_pack', 'remove_pack'.
    """
    op = operation.strip().lower()
    valid_ops = ("set_trash_list", "get_trash_list", "add_pack", "remove_pack")
    if op not in valid_ops:
        return {"ok": False, "error": f"Invalid operation '{operation}'. Supported: {', '.join(valid_ops)}"}

    return await _exec_bridge_sync(
        bot_name=bot_name,
        action="trash_pack_manager",
        params={
            "op": op,
            "items": items or [],
            "pack_name": pack_name,
            "item_id": item_id,
        },
        timeout=10.0,
    )


@mcp.tool()
async def luci_file_system(
    operation: str,
    file_path: str,
    content: str = "",
    bot_name: str = "first",
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    """
    Reads, writes, or appends files inside Lucifer's script sandbox via native read/write/append APIs.
    operation: 'read', 'write', or 'append'.
    """
    op = operation.strip().lower()
    if op not in ("read", "write", "append"):
        return {"ok": False, "error": f"Invalid file operation '{operation}'. Use read, write, or append."}
    return await _exec_bridge_sync(
        bot_name=bot_name,
        action="file_ops",
        params={"op": op, "path": file_path, "content": content},
        timeout=timeout_seconds,
    )


@mcp.tool()
def luci_item_details(item_id_or_name: str) -> Dict[str, Any]:
    """
    Returns full Growtopia metadata for an item ID or name: seed/block pair IDs & names,
    rarity, tier, category, splice recipe, growth time, and in-game description.
    """
    raw = str(item_id_or_name or "").strip()
    details = get_item_details(int(raw) if raw.isdigit() else raw)
    if details is None:
        candidates = search_items(raw, limit=5)
        if not candidates:
            return {"found": False, "query": item_id_or_name, "error": "Item not found."}
        details = get_item_details(int(candidates[0]["id"]))
        if details is None:
            return {"found": False, "query": item_id_or_name, "candidates": candidates}
        details["matched_from_search"] = True

    enriched = dict(details)
    enriched["found"] = True
    sid = enriched.get("seed_id") or get_seed_id(int(enriched["id"]))
    bid = enriched.get("block_id") or get_block_id(int(enriched["id"]))
    if sid is not None:
        enriched["seed_id"] = sid
        enriched["seed_name"] = get_item_name(int(sid))
    if bid is not None:
        enriched["block_id"] = bid
        enriched["block_name"] = get_item_name(int(bid))
    return enriched


@mcp.tool()
def luci_api_docs(query: str, max_matches: int = 15) -> Dict[str, Any]:
    """
    Searches Lucifer v2.88 p2 official documentation files (functions.md, structs.md,
    automations.md, rotation.md, enums.md, AI_TRAINING_LUCIFER.md, lucifer_dumped_api.txt)
    for exact Lua API signatures, properties, and usage examples.
    """
    q = str(query or "").strip()
    if not q:
        available = [p.name for p in sorted(DOCS_DIR.glob("*")) if p.is_file()] if DOCS_DIR.exists() else []
        return {"query": "", "available_docs": available, "matches": []}

    q_low = q.lower()
    doc_candidates = [
        "functions.md",
        "structs.md",
        "automations.md",
        "rotation.md",
        "enums.md",
        "AI_TRAINING_LUCIFER.md",
        "lucifer_dumped_api.txt",
        "lucifer_full_configuration_dump.txt",
    ]

    matches: List[Dict[str, Any]] = []
    for fname in doc_candidates:
        fpath = DOCS_DIR / fname
        if not fpath.exists():
            continue
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for idx, line in enumerate(lines):
            if q_low in line.lower():
                start = max(0, idx - 1)
                end = min(len(lines), idx + 3)
                snippet = "\n".join(lines[start:end])
                matches.append({
                    "file": fname,
                    "line": idx + 1,
                    "snippet": snippet,
                })
                if len(matches) >= max_matches:
                    return {"query": q, "count": len(matches), "matches": matches}

    return {"query": q, "count": len(matches), "matches": matches}


@mcp.tool()
def luci_relay_info() -> Dict[str, Any]:
    """
    Returns the active RelayServer URL, /bridge.lua script URL, active bot count,
    and the ready-to-paste Lucifer Lua Executor connection snippet.
    """
    cfg = _load_server_config()
    srv = cfg.get("server", {}) if isinstance(cfg, dict) else {}
    host = str(srv.get("host") or _INPROCESS_RELAY_HOST or "127.0.0.1")
    port = int(srv.get("relay_port") or _INPROCESS_RELAY_PORT or 8829)
    public_url = str(srv.get("public_url") or "").strip().rstrip("/")

    if public_url:
        base_url = public_url
    elif _EXTERNAL_RELAY_URL:
        base_url = _EXTERNAL_RELAY_URL
    else:
        connect_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
        base_url = f"http://{connect_host}:{port}"

    bridge_url = f"{base_url}/bridge.lua"
    lua_oneliner = (
        f'local c = HttpClient.new()\n'
        f'c.url = "{bridge_url}"\n'
        f'local r = c:request()\n'
        f'load(r and r.body or c.content)()'
    )

    mode = "external_http_proxy" if _EXTERNAL_RELAY_URL else ("in_process" if _INPROCESS_RELAY_SERVER else "standby")
    return {
        "relay_url": base_url,
        "bridge_url": bridge_url,
        "relay_mode": mode,
        "connected_bots": len(fleet_manager.list_bots()) if not _should_use_external_relay() else _http_json_sync("GET", "/api/status").get("total_bots", 0),
        "lucifer_executor_snippet": lua_oneliner,
    }
