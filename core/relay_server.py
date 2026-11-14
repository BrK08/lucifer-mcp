"""
Lucifer Multibot — HTTP Relay & IPC Server
Serves the Web Deck, multi-tenant Lucifer Lua bridge, handles bot heartbeats,
command polling, synchronous command results, and event dispatch.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web

from core.bot_manager import fleet_manager
from core.item_db import get_all_items_catalog, get_item_name
from core.minimap_renderer import render_minimap_bytes
from core.tenant_manager import render_bridge_lua, tenant_manager

ROOT = Path(__file__).resolve().parent.parent
BRIDGE_PATH = ROOT / "bridge" / "lucifer_bridge.lua"
INDEX_HTML_PATH = ROOT / "web" / "index.html"
ASSETS_DIR = ROOT / "assets"


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return response


def _sanitize_external_heartbeat(payload: Dict[str, Any], query_token: str = "") -> Dict[str, Any]:
    """Strip untrusted owner_id from external HTTP payloads; rely only on owner_token."""
    clean = dict(payload)
    clean.pop("owner_id", None)
    if query_token and not clean.get("owner_token") and not clean.get("token"):
        clean["owner_token"] = query_token
    return clean


class RelayServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8829):
        self.host = host
        self.port = port
        self.app = web.Application(middlewares=[cors_middleware])
        self.runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_route("OPTIONS", "/{tail:.*}", self.handle_options)
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/bridge.lua", self.handle_bridge_lua)
        self.app.router.add_get("/api/poll", self.handle_poll)
        self.app.router.add_post("/api/heartbeat", self.handle_heartbeat)
        self.app.router.add_post("/api/command_result", self.handle_command_result)
        self.app.router.add_post("/api/execute", self.handle_execute_sync)
        self.app.router.add_post("/api/event", self.handle_event)
        self.app.router.add_post("/api/command", self.handle_queue_command)
        self.app.router.add_post("/api/fleet/broadcast", self.handle_queue_command)
        self.app.router.add_post("/api/dump", self.handle_dump)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/fleet/summary", self.handle_status)
        self.app.router.add_get("/fleet/summary", self.handle_status)
        self.app.router.add_get("/api/fleet/stats", self.handle_fleet_stats)
        self.app.router.add_get("/api/items", self.handle_items_catalog)

        # Bot specific telemetry endpoints
        self.app.router.add_get("/api/bot/{name}", self.handle_bot_detail)
        self.app.router.add_get("/api/bot/{name}/map", self.handle_bot_map)
        self.app.router.add_get("/api/bot/{name}/inventory", self.handle_bot_inventory)
        self.app.router.add_get("/api/bot/{name}/logs", self.handle_bot_logs)
        self.app.router.add_post("/api/bot/{name}/cmd", self.handle_bot_cmd)

        # Static assets
        if ASSETS_DIR.exists():
            self.app.router.add_static("/assets", str(ASSETS_DIR))

    def _resolve_owner_query(self, request: web.Request) -> Optional[str]:
        token = request.query.get("token", "").strip()
        if token:
            return tenant_manager.resolve_user_by_token(token) or "__invalid_token__"
        owner = request.query.get("owner_id", "").strip()
        return owner or None

    async def handle_options(self, request: web.Request) -> web.Response:
        return web.Response(status=204)

    async def handle_index(self, request: web.Request) -> web.Response:
        # Web Deck UI is currently shelved/disabled by request; expose plain-text relay health only.
        return web.Response(
            text=(
                "Lucifer Multibot Relay Server v2.5 is RUNNING (Web Deck is currently disabled).\n"
                "Bridge URL: /bridge.lua\n"
                "Status URL: /api/status"
            ),
            content_type="text/plain",
        )

    async def handle_bridge_lua(self, request: web.Request) -> web.Response:
        if not BRIDGE_PATH.exists():
            return web.Response(status=404, text="-- lucifer_bridge.lua not found")

        token = request.query.get("token", "").strip()
        server_url = request.query.get("relay", "").strip()
        if not server_url:
            host_hdr = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or ""
            if host_hdr:
                proto = request.headers.get("X-Forwarded-Proto") or request.scheme or "http"
                server_url = f"{proto}://{host_hdr}"

        content = render_bridge_lua(BRIDGE_PATH, token=token, server_url=server_url)
        return web.Response(text=content, content_type="text/plain")

    async def handle_poll(self, request: web.Request) -> web.Response:
        """Lucifer bot calls this to fetch queued commands."""
        bot_name = request.query.get("bot", "global")
        token = request.query.get("token", "").strip()
        owner_id = tenant_manager.resolve_user_by_token(token) if token else None
        commands = fleet_manager.pop_commands_for_bot(bot_name, owner_id=owner_id)
        return web.json_response({"status": "ok", "commands": commands})

    async def handle_heartbeat(self, request: web.Request) -> web.Response:
        """Lucifer bot sends live status (name, world, x, y, gems, level, captcha, etc.)."""
        try:
            data = await request.json()
        except Exception:
            try:
                raw_b = await request.read()
                data = json.loads(raw_b.decode("utf-8", errors="replace"))
            except Exception:
                return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        query_token = request.query.get("token", "").strip()

        if isinstance(data, list):
            commands_by_bot: Dict[str, Any] = {}
            for item in data:
                if isinstance(item, dict):
                    clean = _sanitize_external_heartbeat(item, query_token=query_token)
                    bot = fleet_manager.update_heartbeat(clean)
                    commands_by_bot[bot.name] = fleet_manager.pop_commands_for_bot(
                        bot.name, owner_id=bot.owner_id
                    )
            return web.json_response(
                {"status": "ok", "fleet_size": len(data), "commands": commands_by_bot}
            )

        if not isinstance(data, dict):
            return web.json_response({"status": "error", "message": "payload must be object or list"}, status=400)

        clean = _sanitize_external_heartbeat(data, query_token=query_token)
        bot = fleet_manager.update_heartbeat(clean)
        commands = fleet_manager.pop_commands_for_bot(bot.name, owner_id=bot.owner_id)
        return web.json_response({"status": "ok", "bot": bot.name, "commands": commands})

    async def handle_command_result(self, request: web.Request) -> web.Response:
        """Lucifer bot sends synchronous eval/inspection execution result."""
        try:
            data = await request.json()
        except Exception:
            try:
                raw_b = await request.read()
                data = json.loads(raw_b.decode("utf-8", errors="replace"))
            except Exception:
                return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    fleet_manager.record_command_result(entry)
            return web.json_response({"status": "ok", "recorded": len(data)})

        if isinstance(data, dict):
            fleet_manager.record_command_result(data)
            return web.json_response({"status": "ok", "cmd_id": data.get("cmd_id", "")})

        return web.json_response({"status": "error", "message": "invalid payload"}, status=400)

    async def handle_execute_sync(self, request: web.Request) -> web.Response:
        """Queue a command and await the live execution result from lucifer_bridge.lua."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)

        if not isinstance(data, dict):
            return web.json_response({"ok": False, "error": "invalid json object"}, status=400)

        action = str(data.get("action") or data.get("command") or data.get("type") or "").strip()
        if not action:
            return web.json_response({"ok": False, "error": "action is required"}, status=400)

        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        tok = str(data.get("owner_token") or request.query.get("token") or "").strip()
        if tok:
            owner_id = tenant_manager.resolve_user_by_token(tok) or "__invalid_token__"
        else:
            raw_owner = data.get("owner_id") or request.query.get("owner_id")
            owner_id = str(raw_owner).strip() if raw_owner else None

        try:
            timeout = max(0.5, min(float(data.get("timeout", 12.0)), 60.0))
        except (TypeError, ValueError):
            timeout = 12.0

        bot_name = str(data.get("bot") or data.get("bot_name") or "first").strip()
        if bot_name.lower() == "first":
            candidates = fleet_manager.list_bots(owner_id=owner_id)
            online = [b for b in candidates if b.is_alive or b.status == "online"]
            picked = (online or candidates)[0] if candidates else None
            if not picked:
                return web.json_response(
                    {"ok": False, "error": "No bots connected to relay."},
                    status=404,
                )
            bot_name = picked.name

        result = await fleet_manager.aexecute_and_wait(
            bot_name=bot_name,
            action=action,
            params=params,
            timeout=timeout,
            owner_id=owner_id,
        )
        return web.json_response(result)

    async def handle_event(self, request: web.Request) -> web.Response:
        """Lucifer bot reports an event (captcha encountered, mod joined, packet received)."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        if not isinstance(data, dict):
            return web.json_response({"status": "error", "message": "invalid json object"}, status=400)

        clean = dict(data)
        clean.pop("owner_id", None)
        tok = str(clean.get("owner_token") or request.query.get("token") or "").strip()
        resolved_owner = tenant_manager.resolve_user_by_token(tok) if tok else None
        if resolved_owner:
            clean["owner_id"] = resolved_owner
        elif clean.get("bot"):
            b = fleet_manager.get_bot(str(clean["bot"]))
            if b:
                clean["owner_id"] = b.owner_id

        event_type = clean.get("type", "generic_event")
        fleet_manager.dispatch_event(event_type, clean)
        return web.json_response({"status": "ok"})

    async def handle_queue_command(self, request: web.Request) -> web.Response:
        """External client queues a command for a bot or owner fleet."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        if not isinstance(data, dict):
            return web.json_response({"status": "error", "message": "invalid json object"}, status=400)

        bot_name = data.get("bot") or data.get("bot_name")
        action = str(data.get("action") or data.get("command") or data.get("type") or "").strip()
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        tok = str(data.get("owner_token") or request.query.get("token") or "").strip()
        owner_id = tenant_manager.resolve_user_by_token(tok) if tok else data.get("owner_id")

        if not bot_name or str(bot_name).lower() == "all":
            if owner_id:
                targeted = fleet_manager.queue_broadcast_command(
                    action=action,
                    params=params,
                    filter_online=bool(data.get("filter_online", False)),
                    bot_names=data.get("bots") if isinstance(data.get("bots"), list) else None,
                    owner_id=str(owner_id),
                )
                return web.json_response({"status": "ok", "action": action, "targeted_bots": targeted})

        cmd_id = fleet_manager.queue_command(bot_name, action, params, owner_id=owner_id)
        return web.json_response({"status": "ok", "command_id": cmd_id})

    async def handle_dump(self, request: web.Request) -> web.Response:
        """Receives live API dump from lucifer_api_dumper.lua."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "error", "message": "invalid json"}, status=400)

        dump_path = Path(__file__).resolve().parent.parent / "data" / "dumped_api.json"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✅ [RelayServer] Live API dump received and saved to {dump_path}")
        return web.json_response({"status": "ok", "message": "dump received successfully"})

    async def handle_status(self, request: web.Request) -> web.Response:
        owner_id = self._resolve_owner_query(request)
        summary = fleet_manager.get_fleet_summary(owner_id=owner_id)
        return web.json_response(summary)

    async def handle_fleet_stats(self, request: web.Request) -> web.Response:
        owner_id = self._resolve_owner_query(request)
        activity = fleet_manager.get_fleet_activity_stats(owner_id=owner_id)
        inventory = fleet_manager.get_fleet_inventory_summary(owner_id=owner_id)
        return web.json_response(
            {
                "status": "ok",
                "activity": activity,
                "inventory": inventory,
                "total_bots": activity.get("total_bots", 0),
                "online_bots": activity.get("online_bots", 0),
                "offline_bots": activity.get("offline_bots", 0),
                "total_gems": inventory.get("total_gems", 0),
                "total_items": inventory.get("total_items", 0),
            }
        )

    async def handle_bot_detail(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        owner_id = self._resolve_owner_query(request)
        bot = fleet_manager.get_bot(name, owner_id=owner_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        recent_worlds = fleet_manager.get_recent_worlds(owner_id=bot.owner_id, limit=6)
        return web.json_response({
            "name": bot.name,
            "owner_id": bot.owner_id,
            "status": bot.status,
            "raw_status": bot.raw_status,
            "world": bot.world,
            "x": bot.x,
            "y": bot.y,
            "tile_x": bot.tile_x,
            "tile_y": bot.tile_y,
            "gems": bot.gem_count,
            "pearls": bot.pearl_count,
            "level": bot.level,
            "ping": bot.ping,
            "is_alive": bot.is_alive,
            "last_seen": bot.last_seen,
            "uptime": bot.uptime,
            "automations": dict(bot.automations or {}),
            "recent_worlds": list(bot.recent_worlds or recent_worlds),
            "tiles_rle": bot.tiles if isinstance(bot.tiles, str) else "",
            "players": list(bot.other_players or []),
        })

    async def handle_bot_map(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        owner_id = self._resolve_owner_query(request)
        bot = fleet_manager.get_bot(name, owner_id=owner_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)

        target_pos = (bot.tile_x, bot.tile_y)
        tx_q = request.query.get("tx")
        ty_q = request.query.get("ty")
        if tx_q is not None and ty_q is not None:
            try:
                target_pos = (max(0, min(99, int(tx_q))), max(0, min(59, int(ty_q))))
            except ValueError:
                pass

        img_bytes = render_minimap_bytes(
            tiles=bot.tiles,
            bot_x=bot.x,
            bot_y=bot.y,
            world_name=bot.world or "EXIT",
            is_public=getattr(bot, "is_public", True),
            other_players=bot.other_players,
            target_pos=target_pos,
        )
        return web.Response(body=img_bytes, content_type="image/png")

    async def handle_items_catalog(self, request: web.Request) -> web.Response:
        return web.json_response(get_all_items_catalog())

    async def handle_bot_inventory(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        owner_id = self._resolve_owner_query(request)
        bot = fleet_manager.get_bot(name, owner_id=owner_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
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
        return web.json_response({"bot": bot.name, "item_count": len(items), "items": items})

    async def handle_bot_logs(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        owner_id = self._resolve_owner_query(request)
        bot = fleet_manager.get_bot(name, owner_id=owner_id)
        if not bot:
            return web.json_response({"error": "Bot not found"}, status=404)
        return web.json_response({"bot": bot.name, "logs": bot.last_log or ""})

    @staticmethod
    def _normalize_web_cmd(raw_action: str, params: Dict[str, Any], bot: Any) -> tuple[str, Dict[str, Any]]:
        act = (raw_action or "").strip().lower()
        p = dict(params or {})

        if act == "move":
            if "x" in p and "y" in p:
                return "find_path", {"x": int(p["x"]), "y": int(p["y"])}
            return "move", {"direction": str(p.get("direction", "right")), "steps": int(p.get("steps", 1))}

        if act == "go":
            return "warp", {"world": str(p.get("world", "")).upper(), "id": str(p.get("id", ""))}

        if act == "toggle":
            key_raw = str(p.get("key", "")).strip().lower()
            key_map = {"farm": "auto_farm", "plant": "auto_plant", "collect": "auto_collect"}
            norm_k = key_map.get(key_raw, key_raw)
            cur = bool(bot.automations.get(norm_k, False)) if bot and getattr(bot, "automations", None) else False
            nxt = bool(p["value"]) if "value" in p else (bool(p["enabled"]) if "enabled" in p else not cur)
            if bot and isinstance(getattr(bot, "automations", None), dict):
                bot.automations[norm_k] = nxt
            setting_keys = {
                "auto_reconnect", "legit_mode", "auto_collect", "auto_trash",
                "anti_fire", "anti_toxic", "auto_leave_on_mod",
                "auto_expand_inventory", "ignore_gems", "ignore_essences",
            }
            if norm_k in setting_keys:
                return "set_setting", {"key": norm_k, "value": nxt}
            return "set_automation", {"automation": norm_k, "enabled": nxt}

        if act == "action":
            sub = str(p.get("action", "")).strip().lower()
            tx = int(p.get("x", (bot.tile_x + 1) if bot else 0))
            ty = int(p.get("y", bot.tile_y if bot else 0))
            if sub in ("punch", "break", "hit"):
                return "hit", {"x": tx, "y": ty}
            if sub == "plant":
                return "place", {"x": tx, "y": ty, "item_id": int(p.get("item_id", 4585))}
            if sub:
                return sub, {k: v for k, v in p.items() if k != "action"}

        if act == "say":
            return "say", {"text": str(p.get("text") if "text" in p else p.get("msg", ""))}

        if act in ("drop", "trash"):
            iid = int(p.get("item_id") or p.get("id") or 0)
            cnt = int(p.get("count") or p.get("n") or 1)
            return act, {"item_id": iid, "count": cnt}

        if act == "halt":
            return "stop_script", {}
        if act == "resume":
            return "set_automation", {"automation": "auto_farm", "enabled": True}

        return act, p

    async def handle_bot_cmd(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        owner_id = self._resolve_owner_query(request)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid json"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "Invalid json object"}, status=400)

        raw_action = str(data.get("type") or data.get("action") or "").strip()
        raw_params = data.get("params") if isinstance(data.get("params"), dict) else {
            k: v for k, v in data.items() if k not in ("type", "action", "params")
        }

        target_bot = fleet_manager.get_bot(name, owner_id=owner_id)
        if not target_bot and raw_action.lower() == "add_bot":
            candidates = fleet_manager.list_bots(owner_id=owner_id)
            online = [b for b in candidates if b.is_alive]
            target_bot = (online or candidates)[0] if candidates else None
            if target_bot:
                name = target_bot.name

        if raw_action.lower() in ("halt", "resume") and name.lower() in ("null", "all", ""):
            act, norm_params = self._normalize_web_cmd(raw_action, raw_params, None)
            targeted = fleet_manager.queue_broadcast_command(act, norm_params, owner_id=owner_id)
            return web.json_response({"status": "ok", "action": act, "targeted_bots": targeted})

        action, params = self._normalize_web_cmd(raw_action, raw_params, target_bot)
        cmd_id = fleet_manager.queue_command(name, action, params, owner_id=owner_id)
        if not cmd_id:
            return web.json_response({"error": "Bot not found or unauthorized"}, status=404)
        return web.json_response({"status": "ok", "command_id": cmd_id, "action": action, "params": params, "bot": name})

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"[RelayServer] Lucifer Relay & Web Deck running on http://{self.host}:{self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
