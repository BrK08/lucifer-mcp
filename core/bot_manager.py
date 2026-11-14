"""
Lucifer Multibot — Bot Manager & Fleet Controller
Manages all connected Lucifer bot states, multi-tenant owner isolation,
command queues, synchronous MCP result tracking, event dispatching,
and live status diagnostics based on Lucifer v2.88 p2 enums.
"""
from __future__ import annotations

import asyncio
import itertools
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.enums import BotStatus, GoogleStatus, describe_bot_status, describe_google_status
from core.glserver_client import glserver_client
from core.tenant_manager import tenant_manager

try:
    from core.item_db import get_item_name
except ImportError:
    try:
        from item_db import get_item_name
    except ImportError:
        def get_item_name(item_id: int) -> str:
            return f"Item #{item_id}"


@dataclass
class BotState:
    name: str
    status: str = "offline"
    raw_status: int = 0
    google_status: int = 0
    captcha_status: str = "no_captcha"
    world: str = ""
    x: int = 0
    y: int = 0
    gem_count: int = 0
    pearl_count: int = 0
    voucher_count: int = 0
    level: int = 1
    ping: int = 0
    inventory: List[Dict[str, Any]] = field(default_factory=list)
    automations: Dict[str, Any] = field(default_factory=dict)
    logs: str = ""
    tiles: List[int] = field(default_factory=list)
    tiles_rle: str = ""
    is_public: bool = True
    other_players: List[Dict[str, Any]] = field(default_factory=list)
    last_seen: float = field(default_factory=time.time)
    connected_at: float = field(default_factory=time.time)
    raw_info: Dict[str, Any] = field(default_factory=dict)
    owner_id: str = "local"
    owner_token: str = ""
    recent_worlds: List[str] = field(default_factory=list)

    @property
    def tile_x(self) -> int:
        return self.x // 32 if self.x >= 100 else self.x

    @property
    def tile_y(self) -> int:
        return self.y // 32 if self.y >= 60 else self.y

    @property
    def is_alive(self) -> bool:
        if (time.time() - self.last_seen) >= 30.0:
            return False
        st = str(self.status).lower().strip()
        if st in ("offline", "banned", "account_banned", "suspended", "http_block", "stopped"):
            return False
        if self.raw_status in (BotStatus.ACCOUNT_BANNED, BotStatus.ACCOUNT_SUSPENDED, BotStatus.LOCATION_BANNED):
            return False
        if st == "0" and self.raw_status == BotStatus.OFFLINE:
            return False
        if st in ("online", "in_game", "connected", "94", "1", "23", "ready", "player_entered") or "online" in st:
            return True
        if self.raw_status in (1, 23, 94, 26, 28, 29, 34):
            return True
        return self.status == "online"

    @property
    def is_connected(self) -> bool:
        return self.is_alive

    @property
    def uptime(self) -> float:
        if not self.is_alive:
            return 0.0
        conn_at = self.connected_at or self.last_seen
        return max(0.0, time.time() - conn_at)

    @property
    def last_log(self) -> str:
        return self.logs or ""

    @property
    def has_captcha(self) -> bool:
        return (
            self.captcha_status in ("solving", "wrong", "captcha_requested", "failed")
            or self.status == "captcha_requested"
            or self.raw_status in (BotStatus.CAPTCHA_REQUESTED, BotStatus.SOLVING_CAPTCHA, BotStatus.FAILED_CAPTCHA)
        )

    @property
    def is_http_blocked(self) -> bool:
        return self.status == "http_block" or self.raw_status == BotStatus.HTTP_BLOCK

    @property
    def google_diagnosis(self) -> Dict[str, Any]:
        return glserver_client.diagnose_google_status(self.google_status)

    @property
    def gems(self) -> int:
        return self.gem_count

    @gems.setter
    def gems(self, value: Any):
        try:
            self.gem_count = int(value)
        except (ValueError, TypeError, OverflowError):
            pass

    @property
    def bot_name(self) -> str:
        return self.name


class BotManager:
    """Central multi-tenant fleet manager for all Lucifer bots."""

    def __init__(self):
        self._lock = threading.RLock()
        self._bots: Dict[str, BotState] = {}
        self._command_queues: Dict[str, List[Dict[str, Any]]] = {}
        self._global_queue: List[Dict[str, Any]] = []
        self._owner_global_queues: Dict[str, List[Dict[str, Any]]] = {}
        self._event_subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
        self._history_logs: List[Dict[str, Any]] = []
        self._cmd_seq = itertools.count(1)
        self._command_results: Dict[str, Dict[str, Any]] = {}
        self._command_events: Dict[str, threading.Event] = {}

    def subscribe_event(self, callback: Callable[[str, Dict[str, Any]], None]):
        """Subscribe to live bot events (captchas, mod joins, bans, disconnects)."""
        self._event_subscribers.append(callback)

    def dispatch_event(self, event_type: str, data: Dict[str, Any]):
        """Dispatches an event to all subscribers (e.g. Discord bot notifications)."""
        data["timestamp"] = time.time()
        self._history_logs.append({"type": event_type, "data": data})
        if len(self._history_logs) > 500:
            self._history_logs.pop(0)

        for sub in list(self._event_subscribers):
            try:
                sub(event_type, data)
            except Exception as e:
                print(f"[BotManager] Event dispatch error: {e}")

    def _resolve_owner_from_payload(self, payload: Dict[str, Any]) -> tuple[str, str]:
        """Resolve (owner_id, owner_token) safely from a heartbeat/poll payload."""
        raw_token = str(payload.get("owner_token") or payload.get("token") or "").strip()
        if raw_token:
            resolved = tenant_manager.resolve_user_by_token(raw_token)
            if resolved:
                return resolved, raw_token
        raw_owner = str(payload.get("owner_id") or "").strip()
        if raw_owner:
            return raw_owner, raw_token
        return "local", raw_token

    def _resolve_bot_key(self, name: str, owner_id: Optional[str] = None) -> Optional[str]:
        """Locate the internal storage key for a bot, respecting owner isolation."""
        if not name:
            return None
        target = str(name).strip()
        target_low = target.lower()
        owner_filter = str(owner_id).strip() if owner_id is not None else None

        with self._lock:
            # Fast path when no owner filter and exact key matches
            if owner_filter is None and target in self._bots:
                return target

            # Pass 1: exact bot.name or exact key match respecting owner_filter
            for key, bot in self._bots.items():
                if owner_filter is not None and bot.owner_id != owner_filter:
                    continue
                if bot.name == target or key == target:
                    return key

            # Pass 2: case-insensitive match respecting owner_filter
            for key, bot in self._bots.items():
                if owner_filter is not None and bot.owner_id != owner_filter:
                    continue
                if bot.name.lower() == target_low or key.lower() == target_low:
                    return key
        return None

    def _storage_key_for_heartbeat(self, name: str, owner_id: str) -> str:
        """Choose a collision-free internal key for (owner_id, name)."""
        with self._lock:
            existing_key = self._resolve_bot_key(name, owner_id=owner_id)
            if existing_key is not None:
                return existing_key

            if owner_id != "local":
                if name in self._bots and self._bots[name].owner_id == "local":
                    self._bots[name].owner_id = owner_id
                    return name
            else:
                non_local_matches = [
                    k for k, b in self._bots.items()
                    if b.name.lower() == name.lower() and b.owner_id and b.owner_id != "local"
                ]
                if len(non_local_matches) == 1:
                    return non_local_matches[0]

            if name not in self._bots:
                return name

            # Name already belongs to a different owner_id: avoid hijacking or overwriting
            suffix = owner_id[-6:] if len(owner_id) > 6 else owner_id
            candidate = f"{name}#{suffix}"
            idx = 2
            while candidate in self._bots and self._bots[candidate].owner_id != owner_id:
                candidate = f"{name}#{suffix}_{idx}"
                idx += 1
            return candidate

    def update_heartbeat(self, payload: Dict[str, Any]) -> BotState:
        """Updates or registers a bot from a heartbeat payload."""
        raw_name = payload.get("bot_name")
        if raw_name is None:
            raw_name = payload.get("name")
        if raw_name is None:
            raw_name = payload.get("bot")
        if isinstance(raw_name, str):
            name = raw_name.strip() if raw_name.strip() else "unknown"
        elif isinstance(raw_name, (int, float)):
            name = str(raw_name)
        elif isinstance(raw_name, (list, tuple, dict)):
            try:
                val = str(raw_name).strip()
                name = val if val else "unknown"
            except Exception:
                name = "unknown"
        else:
            name = "unknown"

        resolved_owner_id, owner_token = self._resolve_owner_from_payload(payload)

        with self._lock:
            storage_key = self._storage_key_for_heartbeat(name, resolved_owner_id)
            bot = self._bots.get(storage_key)
            if not bot:
                bot = BotState(
                    name=name,
                    owner_id=resolved_owner_id,
                    owner_token=owner_token,
                )
                self._bots[storage_key] = bot
            else:
                # Rebind owner_token if upgraded/reconnected under the same slot
                if owner_token:
                    bot.owner_token = owner_token
                if resolved_owner_id != "local" and bot.owner_id == "local":
                    bot.owner_id = resolved_owner_id

            old_status = bot.status
            old_captcha = bot.captcha_status
            old_google = bot.google_status

            # Safely capture raw_status first
            if "raw_status" in payload and payload["raw_status"] is not None:
                try:
                    bot.raw_status = int(payload["raw_status"])
                except (ValueError, TypeError, OverflowError):
                    pass

            if "status" in payload and payload["status"] is not None:
                raw_st = str(payload["status"]).strip()
                if raw_st in ("94", "1", "23", "online", "Online", "ONLINE") or bot.raw_status in (1, 23, 94) or "online" in raw_st.lower():
                    if bot.status != "online":
                        bot.connected_at = time.time()
                    bot.status = "online"
                else:
                    bot.status = raw_st
            elif bot.raw_status in (1, 23, 94):
                if bot.status != "online":
                    bot.connected_at = time.time()
                bot.status = "online"

            if "world" in payload and payload["world"] is not None:
                bot.world = str(payload["world"])
                self._record_world(bot, bot.world)

            if "world_public" in payload or "is_public" in payload:
                bot.is_public = bool(payload.get("world_public", payload.get("is_public", True)))

            if "captcha_status" in payload and payload["captcha_status"] is not None:
                bot.captcha_status = str(payload["captcha_status"])

            # Safely coerce gem_count with fallback hierarchy
            gems_val = payload.get("gems")
            if gems_val is not None:
                try:
                    bot.gem_count = int(gems_val)
                except (ValueError, TypeError, OverflowError):
                    gem_raw = payload.get("gem_count")
                    if gem_raw is not None:
                        try:
                            bot.gem_count = int(gem_raw)
                        except (ValueError, TypeError, OverflowError):
                            bot.gem_count = bot.gem_count if isinstance(bot.gem_count, int) else 0
                    else:
                        bot.gem_count = bot.gem_count if isinstance(bot.gem_count, int) else 0
            elif "gem_count" in payload:
                gem_raw = payload.get("gem_count")
                try:
                    bot.gem_count = int(gem_raw)
                except (ValueError, TypeError, OverflowError):
                    bot.gem_count = bot.gem_count if isinstance(bot.gem_count, int) else 0
            else:
                if not isinstance(bot.gem_count, int):
                    bot.gem_count = 0

            # Safe integer conversions for other telemetry fields
            for int_field in (
                "raw_status",
                "google_status",
                "x",
                "y",
                "pearl_count",
                "voucher_count",
                "level",
                "ping",
            ):
                if int_field in payload:
                    try:
                        setattr(bot, int_field, int(payload[int_field]))
                    except (ValueError, TypeError, OverflowError):
                        pass

            if "inventory" in payload:
                bot.inventory = payload["inventory"]
            if "automations" in payload:
                bot.automations = payload["automations"]
            if "logs" in payload and payload["logs"]:
                bot.logs = payload["logs"]

            raw_rle = payload.get("tiles_rle")
            if not raw_rle and isinstance(payload.get("tiles"), str):
                raw_rle = payload.get("tiles")
            if raw_rle:
                bot.tiles_rle = str(raw_rle)
                decoded = []
                for chunk in bot.tiles_rle.split(","):
                    chunk = chunk.strip()
                    if ":" in chunk:
                        try:
                            fg_s, cnt_s = chunk.split(":", 1)
                            decoded.extend([int(fg_s)] * int(cnt_s))
                        except ValueError:
                            pass
                    elif chunk:
                        try:
                            decoded.append(int(chunk))
                        except ValueError:
                            pass
                if decoded:
                    bot.tiles = decoded
            elif "tiles" in payload and isinstance(payload["tiles"], list):
                bot.tiles = payload["tiles"]

            if "players" in payload and isinstance(payload["players"], list):
                bot.other_players = payload["players"]

            bot.last_seen = time.time()
            bot.raw_info = payload

        # Record any completed synchronous/command results sent in heartbeat
        cmd_results = payload.get("command_results")
        if isinstance(cmd_results, list):
            for res in cmd_results:
                if isinstance(res, dict):
                    res.setdefault("bot", bot.name)
                    self.record_command_result(res)

        # Check for critical status changes and dispatch alerts (multi-tenant aware)
        if bot.has_captcha and old_captcha != bot.captcha_status:
            self.dispatch_event(
                "captcha_alert",
                {
                    "bot": bot.name,
                    "owner_id": bot.owner_id,
                    "captcha_status": bot.captcha_status,
                    "captcha_url": payload.get("captcha_url", ""),
                },
            )

        if (bot.status == "mod_entered" or bot.raw_status == BotStatus.MOD_ENTERED) and (
            old_status != bot.status
        ):
            self.dispatch_event(
                "mod_alert",
                {
                    "bot": bot.name,
                    "owner_id": bot.owner_id,
                    "world": bot.world,
                    "msg": "Moderator entered world!",
                },
            )

        if (
            bot.status in ("account_banned", "location_banned", "account_suspended")
            or bot.raw_status in (BotStatus.ACCOUNT_BANNED, BotStatus.LOCATION_BANNED, BotStatus.ACCOUNT_SUSPENDED)
        ) and old_status != bot.status:
            self.dispatch_event(
                "ban_alert",
                {
                    "bot": bot.name,
                    "owner_id": bot.owner_id,
                    "status": bot.status,
                    "msg": "Bot has been banned or suspended!",
                },
            )

        if (bot.status == "banwave_detected" or bot.raw_status == BotStatus.BANWAVE_DETECTED) and (
            old_status != bot.status
        ):
            self.dispatch_event(
                "banwave_alert",
                {
                    "bot": bot.name,
                    "owner_id": bot.owner_id,
                    "msg": "BANWAVE DETECTED! Emergency stop recommended.",
                },
            )

        if bot.is_http_blocked and old_status != bot.status:
            self.dispatch_event(
                "http_block_alert",
                {
                    "bot": bot.name,
                    "owner_id": bot.owner_id,
                    "msg": "HTTP Block (13): Growtopia server_data.php blocked IP.",
                },
            )

        if bot.google_status != 0 and bot.google_status != old_google:
            diag = bot.google_diagnosis
            self.dispatch_event(
                "google_status_alert",
                {
                    "bot": bot.name,
                    "owner_id": bot.owner_id,
                    "diagnosis": diag,
                },
            )

        return bot

    def get_bot(self, name: str, owner_id: Optional[str] = None) -> Optional[BotState]:
        with self._lock:
            key = self._resolve_bot_key(name, owner_id=owner_id)
            return self._bots.get(key) if key is not None else None

    def list_bots(self, owner_id: Optional[str] = None) -> List[BotState]:
        with self._lock:
            if owner_id is None:
                return list(self._bots.values())
            uid = str(owner_id).strip()
            return [b for b in self._bots.values() if b.owner_id == uid]

    def claim_bot(self, bot_name: str, owner_id: str) -> bool:
        """Assign an unclaimed ('local') bot to a specific Discord owner_id."""
        uid = str(owner_id or "").strip()
        if not uid:
            return False
        with self._lock:
            key = self._resolve_bot_key(bot_name, owner_id="local")
            if key is None:
                # Also allow idempotent re-claim if already owned by uid
                owned_key = self._resolve_bot_key(bot_name, owner_id=uid)
                return owned_key is not None
            bot = self._bots.get(key)
            if not bot or bot.owner_id not in ("local", uid):
                return False
            bot.owner_id = uid
            # Merge and prune any stale offline duplicate slots with the same bot name under this owner
            stale_keys = [
                k for k, other in self._bots.items()
                if k != key and other.name.lower() == bot.name.lower() and other.owner_id == uid and not other.is_alive
            ]
            for sk in stale_keys:
                stale_bot = self._bots.pop(sk, None)
                if stale_bot:
                    for w in reversed(stale_bot.recent_worlds):
                        self._record_world(bot, w)
            return True

    def record_command_result(self, result: Dict[str, Any]) -> None:
        """Store execution output from a Lua bridge command and wake any waiter."""
        cmd_id = str(result.get("cmd_id") or result.get("id") or "").strip()
        if not cmd_id:
            return
        with self._lock:
            entry = {
                "cmd_id": cmd_id,
                "bot": result.get("bot", ""),
                "ok": bool(result.get("ok", result.get("error") is None)),
                "result": result.get("result"),
                "output": str(result.get("output") or ""),
                "error": result.get("error"),
                "received_at": time.time(),
            }
            self._command_results[cmd_id] = entry
            if len(self._command_results) > 500:
                oldest = next(iter(self._command_results))
                self._command_results.pop(oldest, None)
            evt = self._command_events.get(cmd_id)
            if evt is not None:
                evt.set()

    def get_command_result(self, cmd_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            res = self._command_results.get(cmd_id)
            return dict(res) if res is not None else None

    def _next_cmd_id(self) -> str:
        return f"cmd_{int(time.time() * 1000)}_{next(self._cmd_seq)}"

    def queue_command(
        self,
        bot_name: Optional[str],
        action: str,
        params: Optional[Dict[str, Any]] = None,
        owner_id: Optional[str] = None,
        cmd_id: Optional[str] = None,
    ) -> str:
        """Queue a command for a specific bot or 'all'/'global', respecting owner isolation."""
        cid = cmd_id or self._next_cmd_id()
        safe_params = params if isinstance(params, dict) else {"value": params} if params is not None else {}
        cmd = {
            "id": cid,
            "cmd_id": cid,
            "action": action,
            "params": safe_params,
            "timestamp": time.time(),
        }

        with self._lock:
            if not bot_name or str(bot_name).strip().lower() in ("all", "global"):
                owner_filter = str(owner_id).strip() if owner_id is not None else None
                target_keys = [
                    k for k, b in self._bots.items()
                    if owner_filter is None or b.owner_id == owner_filter
                ]
                if target_keys:
                    for key in target_keys:
                        if action == "warp" and safe_params.get("world") and key in self._bots:
                            self._record_world(self._bots[key], str(safe_params["world"]))
                        self._command_queues.setdefault(key, []).append(dict(cmd))
                elif owner_filter is not None:
                    self._owner_global_queues.setdefault(owner_filter, []).append(dict(cmd))
                else:
                    self._global_queue.append(dict(cmd))
                return cid

            key = self._resolve_bot_key(str(bot_name), owner_id=owner_id)
            if key is not None:
                if action == "warp" and safe_params.get("world") and key in self._bots:
                    self._record_world(self._bots[key], str(safe_params["world"]))
                self._command_queues.setdefault(key, []).append(cmd)
                return cid

            if owner_id is None:
                self._command_queues.setdefault(str(bot_name), []).append(cmd)
                return cid

            # Strict multi-tenant block: requested bot does not belong to owner_id
            return ""

    def pop_commands_for_bot(
        self,
        bot_name: str,
        owner_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Pops pending commands for a specific bot (respecting owner_id when known)."""
        cmds: List[Dict[str, Any]] = []
        with self._lock:
            key = self._resolve_bot_key(bot_name, owner_id=owner_id)
            bot = self._bots.get(key) if key is not None else None
            effective_owner = str(owner_id) if owner_id is not None else (bot.owner_id if bot else None)

            if self._global_queue:
                cmds.extend(self._global_queue)
                self._global_queue.clear()

            if effective_owner and self._owner_global_queues.get(effective_owner):
                oq = self._owner_global_queues[effective_owner]
                cmds.extend(oq)
                oq.clear()

            lookup_key = key if key is not None else bot_name
            q = self._command_queues.get(lookup_key)
            if q:
                cmds.extend(q)
                q.clear()
        return cmds

    def execute_and_wait(
        self,
        bot_name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 12.0,
        owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronously queue a command and block until the bridge returns its result."""
        cid = self._next_cmd_id()
        evt = threading.Event()
        with self._lock:
            self._command_events[cid] = evt
            queued_id = self.queue_command(
                bot_name=bot_name,
                action=action,
                params=params,
                owner_id=owner_id,
                cmd_id=cid,
            )
            if not queued_id:
                self._command_events.pop(cid, None)
                return {
                    "ok": False,
                    "cmd_id": "",
                    "error": f"Bot '{bot_name}' not found or not authorized for this owner.",
                }

        signaled = evt.wait(timeout=timeout)
        with self._lock:
            self._command_events.pop(cid, None)
            if signaled and cid in self._command_results:
                return dict(self._command_results[cid])

        return {
            "ok": False,
            "timeout": True,
            "cmd_id": cid,
            "error": (
                f"Timed out after {timeout:.1f}s waiting for '{bot_name}' response. "
                "Make sure Lucifer is running lucifer_bridge.lua."
            ),
        }

    async def aexecute_and_wait(
        self,
        bot_name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 12.0,
        owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async version of execute_and_wait that does not block the asyncio event loop."""
        cid = self._next_cmd_id()
        evt = threading.Event()
        with self._lock:
            self._command_events[cid] = evt
            queued_id = self.queue_command(
                bot_name=bot_name,
                action=action,
                params=params,
                owner_id=owner_id,
                cmd_id=cid,
            )
            if not queued_id:
                self._command_events.pop(cid, None)
                return {
                    "ok": False,
                    "cmd_id": "",
                    "error": f"Bot '{bot_name}' not found or not authorized for this owner.",
                }

        deadline = time.monotonic() + max(0.2, float(timeout))
        while not evt.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)

        with self._lock:
            self._command_events.pop(cid, None)
            if evt.is_set() and cid in self._command_results:
                return dict(self._command_results[cid])

        return {
            "ok": False,
            "timeout": True,
            "cmd_id": cid,
            "error": (
                f"Timed out after {timeout:.1f}s waiting for '{bot_name}' response. "
                "Make sure Lucifer is running lucifer_bridge.lua."
            ),
        }

    def queue_broadcast_command(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        filter_online: bool = True,
        bot_names: Optional[List[str]] = None,
        owner_id: Optional[str] = None,
    ) -> int:
        """
        Queues a broadcast command across connected bots (scoped to owner_id when set).
        If filter_online is True (default), targets only bots that are currently alive.
        """
        if params is None:
            params = {}

        owner_filter = str(owner_id).strip() if owner_id is not None else None
        with self._lock:
            if bot_names is not None:
                candidate_keys = []
                for nm in bot_names:
                    k = self._resolve_bot_key(str(nm), owner_id=owner_filter)
                    if k is not None:
                        candidate_keys.append(k)
            else:
                candidate_keys = [
                    k for k, b in self._bots.items()
                    if owner_filter is None or b.owner_id == owner_filter
                ]

            targeted_count = 0
            for key in candidate_keys:
                bot = self._bots.get(key)
                if not bot:
                    continue
                if filter_online and not bot.is_alive:
                    continue
                if action == "warp" and params.get("world"):
                    self._record_world(bot, str(params["world"]))
                cid = self._next_cmd_id()
                cmd = {
                    "id": cid,
                    "cmd_id": cid,
                    "action": action,
                    "params": dict(params),
                    "timestamp": time.time(),
                }
                self._command_queues.setdefault(key, []).append(cmd)
                targeted_count += 1

        return targeted_count

    def get_fleet_inventory_summary(self, owner_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Aggregates total gems, pearls, vouchers, and item inventories across connected bots.
        """
        bots = self.list_bots(owner_id=owner_id)
        total_gems = 0
        total_pearls = 0
        total_vouchers = 0
        aggregated_items: Dict[int, Dict[str, Any]] = {}
        by_bot: Dict[str, Dict[str, Any]] = {}

        for b in bots:
            if (
                isinstance(b.gem_count, (int, float))
                and not isinstance(b.gem_count, bool)
                and not math.isinf(b.gem_count)
                and not math.isnan(b.gem_count)
            ):
                total_gems += int(b.gem_count)

            if (
                isinstance(b.pearl_count, (int, float))
                and not isinstance(b.pearl_count, bool)
                and not math.isinf(b.pearl_count)
                and not math.isnan(b.pearl_count)
            ):
                total_pearls += int(b.pearl_count)

            if (
                isinstance(b.voucher_count, (int, float))
                and not isinstance(b.voucher_count, bool)
                and not math.isinf(b.voucher_count)
                and not math.isnan(b.voucher_count)
            ):
                total_vouchers += int(b.voucher_count)

            bot_items_total = 0
            if isinstance(b.inventory, list):
                for it in b.inventory:
                    if not isinstance(it, dict):
                        continue
                    raw_id = it.get("id") if it.get("id") is not None else it.get("item_id", 0)
                    try:
                        iid = int(raw_id)
                    except (ValueError, TypeError, OverflowError):
                        iid = 0

                    raw_cnt = it.get("count") if it.get("count") is not None else it.get("amount", 0)
                    try:
                        cnt = int(raw_cnt)
                    except (ValueError, TypeError, OverflowError):
                        cnt = 0

                    if cnt < 0:
                        cnt = 0

                    name = it.get("name") or get_item_name(iid)
                    if iid not in aggregated_items:
                        aggregated_items[iid] = {"id": iid, "name": name, "count": 0}
                    aggregated_items[iid]["count"] += cnt
                    bot_items_total += cnt

            by_bot[b.name] = {
                "gems": b.gem_count,
                "pearls": b.pearl_count,
                "item_count": bot_items_total,
                "is_alive": b.is_alive,
            }

        sorted_items = sorted(aggregated_items.values(), key=lambda x: x["count"], reverse=True)
        total_items_count = sum(it["count"] for it in sorted_items)

        return {
            "total_bots": len(bots),
            "online_bots": sum(1 for b in bots if b.is_alive),
            "total_gems": total_gems,
            "total_pearls": total_pearls,
            "total_vouchers": total_vouchers,
            "total_items": total_items_count,
            "unique_items": len(sorted_items),
            "items": sorted_items,
            "by_bot": by_bot,
        }

    def get_fleet_activity_stats(self, owner_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculates fleet-wide activity metrics: uptime statistics, world distribution,
        status breakdown, active farming counts, and network latency averages.
        """
        bots = self.list_bots(owner_id=owner_id)
        now = time.time()
        online_bots = [b for b in bots if b.is_alive]
        offline_bots = [b for b in bots if not b.is_alive]

        world_dist: Dict[str, int] = {}
        status_dist: Dict[str, int] = {}
        active_farming = 0
        total_ping = 0
        ping_count = 0
        uptimes: List[float] = []

        for b in bots:
            st = str(b.status).lower().strip() if b.status else "offline"
            status_dist[st] = status_dist.get(st, 0) + 1

            w = str(b.world).strip() if b.world and str(b.world).strip() else "NONE"
            world_dist[w] = world_dist.get(w, 0) + 1

            is_farming = False
            if isinstance(b.automations, dict) and b.automations.get("auto_farm"):
                is_farming = True
            elif b.status in ("farming", "farm", "auto_farm"):
                is_farming = True
            if is_farming and b.is_alive:
                active_farming += 1

            if b.is_alive and isinstance(b.ping, (int, float)) and b.ping > 0:
                total_ping += b.ping
                ping_count += 1

            if b.is_alive:
                conn_at = getattr(b, "connected_at", b.last_seen)
                up_sec = max(0.0, now - conn_at)
                uptimes.append(up_sec)

        avg_ping = round(total_ping / ping_count, 1) if ping_count > 0 else 0.0
        avg_uptime = round(sum(uptimes) / len(uptimes), 1) if uptimes else 0.0
        max_uptime = round(max(uptimes), 1) if uptimes else 0.0
        total_uptime = round(sum(uptimes), 1)

        worlds_list = sorted([w for w in world_dist.keys() if w != "NONE"])

        return {
            "total_bots": len(bots),
            "online_bots": len(online_bots),
            "offline_bots": len(offline_bots),
            "world_distribution": world_dist,
            "status_breakdown": status_dist,
            "active_farming_bots": active_farming,
            "worlds": worlds_list,
            "average_ping": avg_ping,
            "uptime": {
                "total_seconds": total_uptime,
                "average_seconds": avg_uptime,
                "max_seconds": max_uptime,
                "tracked_bots": len(uptimes),
            },
            "total_uptime_seconds": total_uptime,
            "average_uptime_seconds": avg_uptime,
            "captcha_alerts": sum(1 for b in bots if b.has_captcha),
            "http_blocked_bots": sum(1 for b in bots if b.is_http_blocked),
        }

    @staticmethod
    def _record_world(bot: BotState, world_name: str) -> None:
        """Track recently visited or warped worlds on a bot (most recent first, max 6)."""
        w = str(world_name or "").strip().upper()
        if not w or w in ("EXIT", "-", "UNKNOWN"):
            return
        if w in bot.recent_worlds:
            bot.recent_worlds.remove(w)
        bot.recent_worlds.insert(0, w)
        if len(bot.recent_worlds) > 6:
            del bot.recent_worlds[6:]

    def get_recent_worlds(self, owner_id: Optional[str] = None, limit: int = 5) -> List[str]:
        """Collect up to `limit` unique recently visited worlds for an owner's fleet."""
        bots = self.list_bots(owner_id=owner_id)
        seen: List[str] = []
        with self._lock:
            for b in bots:
                cur = str(b.world or "").strip().upper()
                if cur and cur not in ("EXIT", "-", "UNKNOWN") and cur not in seen:
                    seen.append(cur)
                for w in b.recent_worlds:
                    wu = str(w or "").strip().upper()
                    if wu and wu not in ("EXIT", "-", "UNKNOWN") and wu not in seen:
                        seen.append(wu)
                    if len(seen) >= limit:
                        return seen[:limit]
        return seen[:limit]

    def get_fleet_summary(self, owner_id: Optional[str] = None) -> Dict[str, Any]:
        bots = self.list_bots(owner_id=owner_id)
        online_count = sum(1 for b in bots if b.is_alive)
        total_gems = sum(
            b.gem_count
            if isinstance(b.gem_count, (int, float))
            and not isinstance(b.gem_count, bool)
            and not math.isinf(b.gem_count)
            and not math.isnan(b.gem_count)
            else 0
            for b in bots
        )
        captcha_count = sum(1 for b in bots if b.has_captcha)
        http_block_count = sum(1 for b in bots if b.is_http_blocked)

        return {
            "total_bots": len(bots),
            "online_bots": online_count,
            "offline_bots": len(bots) - online_count,
            "captcha_alerts": captcha_count,
            "http_blocked_bots": http_block_count,
            "total_gems": total_gems,
            "bots": [
                {
                    "name": b.name,
                    "owner_id": b.owner_id,
                    "status": b.status,
                    "raw_status": b.raw_status,
                    "google_status": b.google_status,
                    "world": b.world,
                    "is_public": b.is_public,
                    "x": b.x,
                    "y": b.y,
                    "pos": f"({b.x},{b.y})",
                    "gems": b.gem_count,
                    "pearls": b.pearl_count,
                    "level": b.level,
                    "ping": b.ping,
                    "automations": dict(b.automations),
                    "recent_worlds": list(b.recent_worlds),
                    "uptime": b.uptime,
                    "last_seen": b.last_seen,
                    "is_alive": b.is_alive,
                    "is_http_blocked": b.is_http_blocked,
                }
                for b in bots
            ],
        }


# Global singleton instance
fleet_manager = BotManager()
