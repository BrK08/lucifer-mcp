"""
Comprehensive tests for Multi-Tenant Isolation, Authentic Growtopia Search Emojis,
Relay Synchronous Execution (/api/execute, /api/command_result), and Full-Access
Human-Equivalent Lucifer MCP Tools.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.test_utils import TestClient, TestServer

from core.bot_manager import BotManager, BotState, fleet_manager
from core.relay_server import RelayServer
from core.tenant_manager import (
    TenantManager,
    render_bridge_lua,
    sanitize_bridge_token,
    sanitize_server_url,
    tenant_manager,
)
_HAS_DISCORD_BOT = importlib.util.find_spec("discord_bot") is not None and importlib.util.find_spec("discord") is not None
if _HAS_DISCORD_BOT:
    from discord_bot.emoji_manager import ASSETS_EMOJI_DIR, clear_emoji_cache, get_item_emoji
else:
    ASSETS_EMOJI_DIR = Path(".")
    clear_emoji_cache = lambda: None
    get_item_emoji = None
from mcp_server import server as mcp_srv


class TestTenantManagerAndBridgeRendering(unittest.TestCase):
    def test_token_lifecycle_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "user_tenants.json"
            tm = TenantManager(storage_path=store_path)

            t1 = tm.get_or_create_token("111222333", alias="Alice")
            t2 = tm.get_or_create_token("444555666", alias="Bob")
            self.assertTrue(t1.startswith("luci_"))
            self.assertNotEqual(t1, t2)
            self.assertEqual(tm.resolve_user_by_token(t1), "111222333")
            self.assertEqual(tm.resolve_user_by_token(t2), "444555666")
            self.assertIsNone(tm.resolve_user_by_token("invalid_token"))

            # Reload from disk
            tm2 = TenantManager(storage_path=store_path)
            self.assertEqual(tm2.resolve_user_by_token(t1), "111222333")

            # Regenerate revokes old token
            t1_new = tm2.regenerate_token("111222333")
            self.assertNotEqual(t1, t1_new)
            self.assertIsNone(tm2.resolve_user_by_token(t1))
            self.assertEqual(tm2.resolve_user_by_token(t1_new), "111222333")

    def test_lua_sanitization_blocks_injection(self):
        self.assertEqual(sanitize_bridge_token('abc";os.execute("rm")'), "")
        self.assertEqual(sanitize_bridge_token("luci_valid_Token-123"), "luci_valid_Token-123")
        self.assertEqual(
            sanitize_server_url('http://example.com:8829"\nprint(1)'),
            "",
        )
        self.assertEqual(
            sanitize_server_url("https://relay.example.com/"),
            "https://relay.example.com",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_lua = Path(tmpdir) / "bridge.lua"
            dummy_lua.write_text(
                'local SERVER_URL = "http://127.0.0.1:8829"\nlocal OWNER_TOKEN = ""\n',
                encoding="utf-8",
            )
            rendered = render_bridge_lua(
                dummy_lua,
                token="luci_safe_token_123",
                server_url="https://relay.example.com",
            )
            self.assertIn('local SERVER_URL = "https://relay.example.com"', rendered)
            self.assertIn('local OWNER_TOKEN = "luci_safe_token_123"', rendered)

            # Malicious token/URL must be rejected (leaving safe defaults intact)
            rendered_blocked = render_bridge_lua(
                dummy_lua,
                token='evil";os.execute("calc")',
                server_url='http://evil.com"\nerror(1)',
            )
            self.assertIn('local SERVER_URL = "http://127.0.0.1:8829"', rendered_blocked)
            self.assertIn('local OWNER_TOKEN = ""', rendered_blocked)


class TestMultiTenantBotManagerAndSyncExec(unittest.TestCase):
    def test_same_bot_name_across_two_tenants_no_collision(self):
        bm = BotManager()
        with patch.object(tenant_manager, "resolve_user_by_token") as mock_res:
            mock_res.side_effect = lambda tok: {"tok_alice": "1001", "tok_bob": "2002"}.get(tok)

            b_alice = bm.update_heartbeat(
                {"bot_name": "MinerBot", "owner_token": "tok_alice", "status": "online", "world": "ALICEWORLD", "gems": 500}
            )
            b_bob = bm.update_heartbeat(
                {"bot_name": "MinerBot", "owner_token": "tok_bob", "status": "online", "world": "BOBWORLD", "gems": 900}
            )

            self.assertEqual(b_alice.owner_id, "1001")
            self.assertEqual(b_bob.owner_id, "2002")
            self.assertEqual(len(bm.list_bots(owner_id="1001")), 1)
            self.assertEqual(len(bm.list_bots(owner_id="2002")), 1)
            self.assertEqual(bm.get_bot("MinerBot", owner_id="1001").world, "ALICEWORLD")
            self.assertEqual(bm.get_bot("MinerBot", owner_id="2002").world, "BOBWORLD")

            # Command queued for Alice never leaks to Bob
            cid = bm.queue_command("MinerBot", "warp", {"world": "FARM_A"}, owner_id="1001")
            self.assertTrue(cid)
            bob_cmds = bm.pop_commands_for_bot("MinerBot", owner_id="2002")
            alice_cmds = bm.pop_commands_for_bot("MinerBot", owner_id="1001")
            self.assertEqual(len(bob_cmds), 0)
            self.assertEqual(len(alice_cmds), 1)
            self.assertEqual(alice_cmds[0]["params"]["world"], "FARM_A")

    def test_all_queue_fanout_delivers_to_every_bot(self):
        bm = BotManager()
        bm.update_heartbeat({"bot_name": "Bot1", "owner_id": "u1", "status": "online"})
        bm.update_heartbeat({"bot_name": "Bot2", "owner_id": "u1", "status": "online"})
        bm.update_heartbeat({"bot_name": "OtherBot", "owner_id": "u2", "status": "online"})

        bm.queue_command("all", "say", {"text": "hello"}, owner_id="u1")

        c1 = bm.pop_commands_for_bot("Bot1", owner_id="u1")
        c2 = bm.pop_commands_for_bot("Bot2", owner_id="u1")
        c3 = bm.pop_commands_for_bot("OtherBot", owner_id="u2")
        self.assertEqual(len(c1), 1)
        self.assertEqual(len(c2), 1)
        self.assertEqual(len(c3), 0)

    def test_bot_state_properties_and_execute_and_wait(self):
        bm = BotManager()
        b = bm.update_heartbeat(
            {"bot_name": "SyncBot", "status": "online", "logs": "[Log] ready"}
        )
        self.assertTrue(b.is_connected)
        self.assertGreaterEqual(b.uptime, 0.0)
        self.assertEqual(b.last_log, "[Log] ready")

        def _respond():
            time.sleep(0.08)
            cmds = bm.pop_commands_for_bot("SyncBot", owner_id=b.owner_id)
            for cmd in cmds:
                bm.record_command_result(
                    {"cmd_id": cmd["cmd_id"], "bot": "SyncBot", "ok": True, "result": 42, "output": "ok"}
                )

        t = threading.Thread(target=_respond, daemon=True)
        t.start()
        res = bm.execute_and_wait("SyncBot", "eval_sync", {"code": "return 42"}, timeout=2.0)
        self.assertTrue(res["ok"])
        self.assertEqual(res["result"], 42)
        self.assertEqual(res["output"], "ok")


class TestRelayMultiTenantHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_bots = dict(fleet_manager._bots)
        self._orig_queues = dict(fleet_manager._command_queues)
        fleet_manager._bots.clear()
        fleet_manager._command_queues.clear()

        self.relay = RelayServer()
        self.client = TestClient(TestServer(self.relay.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        fleet_manager._bots.clear()
        fleet_manager._bots.update(self._orig_bots)
        fleet_manager._command_queues.clear()
        fleet_manager._command_queues.update(self._orig_queues)

    async def test_dynamic_bridge_lua_and_untrusted_owner_stripping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_tm = TenantManager(storage_path=Path(tmpdir) / "tenants.json")
            tok = local_tm.get_or_create_token("777888999", alias="Charlie")
            with patch("core.relay_server.tenant_manager", local_tm), patch(
                "core.bot_manager.tenant_manager", local_tm
            ):
                resp = await self.client.get(f"/bridge.lua?token={tok}")
                self.assertEqual(resp.status, 200)
                lua_src = await resp.text()
                self.assertIn(f'local OWNER_TOKEN = "{tok}"', lua_src)

                # Verify rendered bridge.lua compiles cleanly in real Lua 5.x runtime
                from lupa import LuaRuntime
                lua = LuaRuntime()
                chunk = lua.eval("load")(lua_src)
                self.assertIsNotNone(chunk)

                # Spoofed owner_id must be stripped in favor of owner_token
                hb = await self.client.post(
                    "/api/heartbeat",
                    json={
                        "bot_name": "CharlieBot",
                        "owner_id": "victim_999",
                        "owner_token": tok,
                        "status": "online",
                        "world": "SECRET",
                    },
                )
                self.assertEqual(hb.status, 200)
                bot = fleet_manager.get_bot("CharlieBot", owner_id="777888999")
                self.assertIsNotNone(bot)
                self.assertEqual(bot.owner_id, "777888999")
                self.assertIsNone(fleet_manager.get_bot("CharlieBot", owner_id="victim_999"))

    async def test_api_execute_and_command_result_roundtrip(self):
        fleet_manager.update_heartbeat({"bot_name": "HttpExecBot", "status": "online"})

        async def _simulate_bridge_poller():
            await asyncio.sleep(0.08)
            poll = await self.client.get("/api/poll?bot=HttpExecBot")
            pdata = await poll.json()
            cmds = pdata.get("commands", [])
            self.assertEqual(len(cmds), 1)
            cid = cmds[0]["cmd_id"]
            post_res = await self.client.post(
                "/api/command_result",
                json={"cmd_id": cid, "bot": "HttpExecBot", "ok": True, "result": {"hello": "world"}, "output": "done"},
            )
            self.assertEqual(post_res.status, 200)

        poller_task = asyncio.create_task(_simulate_bridge_poller())
        exec_resp = await self.client.post(
            "/api/execute",
            json={"bot": "first", "action": "eval_sync", "params": {"code": "return {hello='world'}"}, "timeout": 3.0},
        )
        await poller_task
        self.assertEqual(exec_resp.status, 200)
        body = await exec_resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"], {"hello": "world"})


class TestGrowtopiaEmojisAndDiscordSearch(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        clear_emoji_cache()

    def test_authentic_item_emoji_mapping_and_seed_sprite(self):
        self.assertTrue((ASSETS_EMOJI_DIR / "gt_seed.png").exists())
        with patch("discord_bot.emoji_manager.load_configured_emojis", return_value={}):
            clear_emoji_cache()
            # Item 240 is Sack O' Joy, NOT Big Lock (204)
            e_sack = get_item_emoji(240, "Sack O' Joy")
            e_big_lock = get_item_emoji(204, "Big Lock")
            e_wl = get_item_emoji(242, "World Lock")
            e_dl = get_item_emoji(1796, "Diamond Lock")
            e_bgl = get_item_emoji(7188, "Blue Gem Lock")
            e_seed = get_item_emoji(4585, "Pepper Tree Seed", is_seed=True)
            self.assertEqual(e_wl, "🔒")
            self.assertEqual(e_dl, "💎🔒")
            self.assertEqual(e_bgl, "🔷🔒")
            self.assertEqual(e_seed, "🌱")
            self.assertNotEqual(e_sack, e_big_lock)

    async def test_discord_search_embed_and_bagla_isolation(self):
        from discord_bot.bot import LuciferDiscordBot

        bot = LuciferDiscordBot({"prefix": "!", "public_relay_url": "https://relay.example.org"})
        with patch("discord_bot.emoji_manager._APP_EMOJI_CACHE", {"gt_wl": "<:gt_wl:123456>", "gt_seed": "<:gt_seed:654321>"}):
            embed, file_obj, view = bot.build_search_embed("World Lock")
            self.assertIsNotNone(embed)
            self.assertIn("Eşya Arama Sonuçları", embed.title)
            self.assertIn("<:gt_wl:123456>", embed.description)
            self.assertIsNotNone(file_obj)
            self.assertIsNotNone(view)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_tm = TenantManager(storage_path=Path(tmpdir) / "tenants.json")
            with patch("discord_bot.bot.tenant_manager", tmp_tm):
                bagla_embed = bot._build_bagla_embed(owner_id="999888777", alias="Tester", is_tr=True)
                all_text = (bagla_embed.description or "") + "\n" + "\n".join(
                    f"{f.name}\n{f.value}" for f in bagla_embed.fields
                )
                self.assertIn("https://relay.example.org/bridge.lua?token=luci_", all_text)
                self.assertIn("local r = c:request(); load(r and r.body or c.content)()", all_text)


class TestFullLuciferMCPTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._orig_bots = dict(fleet_manager._bots)
        self._orig_queues = dict(fleet_manager._command_queues)
        fleet_manager._bots.clear()
        fleet_manager._command_queues.clear()
        fleet_manager.update_heartbeat({"bot_name": "MCPBot", "status": "online", "world": "START", "logs": "old_log"})

    def tearDown(self):
        fleet_manager._bots.clear()
        fleet_manager._bots.update(self._orig_bots)
        fleet_manager._command_queues.clear()
        fleet_manager._command_queues.update(self._orig_queues)

    def _spawn_responder(self, result_val, output_val=""):
        def _worker():
            for _ in range(40):
                cmds = fleet_manager.pop_commands_for_bot("MCPBot", owner_id="local")
                if cmds:
                    for c in cmds:
                        fleet_manager.record_command_result(
                            {"cmd_id": c["cmd_id"], "bot": "MCPBot", "ok": True, "result": result_val, "output": output_val}
                        )
                    return
                time.sleep(0.02)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    async def test_eval_sync_world_tile_count_and_console_tools(self):
        self._spawn_responder(result_val={"gems": 1234}, output_val="Printed from Lua")
        eval_res = await mcp_srv.luci_eval_sync('print("Printed from Lua"); return {gems=1234}', timeout_seconds=3.0)
        self.assertTrue(eval_res["ok"])
        self.assertEqual(eval_res["result"], {"gems": 1234})
        self.assertEqual(eval_res["output"], "Printed from Lua")

        self._spawn_responder(
            result_val={
                "name": "START",
                "players": [{"name": "Tester", "x": 10, "y": 20}],
                "tile_summary": [{"id": 242, "count": 2}],
                "objects": [{"id": 4584, "count": 20, "x": 5, "y": 5}],
            }
        )
        world_res = await mcp_srv.luci_inspect_world(timeout_seconds=3.0)
        self.assertTrue(world_res["ok"])
        self.assertEqual(world_res["result"]["tile_summary"][0]["name"], "World Lock")
        self.assertEqual(world_res["result"]["objects"][0]["name"], "Pepper Tree")

        self._spawn_responder(result_val={"x": 5, "y": 5, "fg": 4584, "bg": 14, "ready": True})
        tile_res = await mcp_srv.luci_inspect_tile(5, 5, timeout_seconds=3.0)
        self.assertEqual(tile_res["result"]["fg_name"], "Pepper Tree")

        self._spawn_responder(result_val={"world": "START", "item_id": 4584, "tile_fg_count": 100})
        cnt_res = await mcp_srv.luci_world_count_item("Pepper Tree", timeout_seconds=3.0)
        self.assertEqual(cnt_res["result"]["item_name"], "Pepper Tree")
        self.assertEqual(cnt_res["result"]["tile_fg_count"], 100)

        self._spawn_responder(result_val={"bot_log": "[Log] line 1", "console": "con line 2"})
        logs_res = await mcp_srv.luci_get_console_and_logs(clear_after=False, live_fetch=True)
        self.assertTrue(logs_res["live"])
        self.assertEqual(logs_res["console"], "con line 2")

    async def test_human_action_and_subsystem_tools(self):
        msg_move = mcp_srv.luci_move("MCPBot", direction="right", steps=3, face_left=False)
        self.assertIn("Move command queued", msg_move)
        msg_equip = mcp_srv.luci_equipment("wear", "World Lock", "MCPBot")
        self.assertIn("wear queued", msg_equip)
        msg_pkt = mcp_srv.luci_send_packet(2, "action|respawn\n", "MCPBot")
        self.assertIn("sendPacket", msg_pkt)
        fleet_manager.pop_commands_for_bot("MCPBot", owner_id="local")

        self._spawn_responder(result_val={"subsystem": "rotation", "applied": ["one_by_one"], "failed": []})
        rot_res = await mcp_srv.luci_configure_rotation(enabled=True, settings={"one_by_one": True}, bot_name="MCPBot")
        self.assertTrue(rot_res["ok"])

        self._spawn_responder(result_val="ok")
        wm_res = await mcp_srv.luci_world_manager("add_farm", world="myfarm1", item_id_or_name="Pepper Tree", bot_name="MCPBot")
        self.assertTrue(wm_res["ok"])

        self._spawn_responder(result_val="file contents")
        fs_res = await mcp_srv.luci_file_system("read", "notes.txt", bot_name="MCPBot")
        self.assertEqual(fs_res["result"], "file contents")

    def test_static_analysis_docs_item_details_and_cli_help(self):
        bad_analysis = mcp_srv.luci_code_analyze("bot:say('Merhaba Türkçe')\nbot:collectItems(2)\nsleep(50)\nbot:hit(1,1)")
        self.assertFalse(bad_analysis["ascii_valid"])
        self.assertFalse(bad_analysis["ok_for_lucifer"])
        self.assertGreater(len(bad_analysis["warnings"]), 0)
        self.assertGreater(len(bad_analysis["ban_risks"]), 0)

        details = mcp_srv.luci_item_details("Pepper Tree")
        self.assertTrue(details["found"])
        self.assertEqual(details["id"], 4584)
        self.assertEqual(details["seed_id"], 4585)

        docs = mcp_srv.luci_api_docs("findPath", max_matches=5)
        self.assertGreater(docs["count"], 0)

        relay_meta = mcp_srv.luci_relay_info()
        self.assertIn("/bridge.lua", relay_meta["bridge_url"])
        self.assertIn("local r = c:request()", relay_meta["lucifer_executor_snippet"])

        # Verify start_mcp.py --help works cleanly
        start_mcp_path = Path(__file__).resolve().parent.parent / "start_mcp.py"
        proc = subprocess.run(
            [sys.executable, str(start_mcp_path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--stdio", proc.stdout)


class TestNaturalActionAndHeartbeatUpgrade(unittest.IsolatedAsyncioTestCase):
    def test_heartbeat_upgrades_local_slot_without_duplicate(self):
        mgr = BotManager()
        mgr.update_heartbeat({"bot_name": "Berkimmm", "status": "retrieving_token", "raw_status": 34})
        self.assertEqual(len(mgr.list_bots()), 1)
        self.assertEqual(mgr.list_bots()[0].owner_id, "local")

        # Heartbeat arrives with real Discord owner_id: upgrades in place rather than creating Berkimmm#...
        mgr.update_heartbeat({
            "bot_name": "Berkimmm",
            "owner_id": "710105435759181944",
            "status": "online",
            "raw_status": 1,
        })
        bots = mgr.list_bots()
        self.assertEqual(len(bots), 1)
        self.assertEqual(bots[0].owner_id, "710105435759181944")

        # Subsequent heartbeat omitting owner_id ("local") reuses existing non-local owner slot
        mgr.update_heartbeat({"bot_name": "Berkimmm", "status": "online", "gems": 777})
        bots_after = mgr.list_bots()
        self.assertEqual(len(bots_after), 1)
        self.assertEqual(bots_after[0].owner_id, "710105435759181944")
        self.assertEqual(bots_after[0].gem_count, 777)

    async def test_parse_and_execute_natural_bot_actions(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from discord_bot.bot import LuciferDiscordBot

        bot_inst = LuciferDiscordBot({"prefix": "!", "relay_url": "http://127.0.0.1:8829"})
        bot_inst.forward_command_to_relay = AsyncMock()

        # Verify parser distinguishes direct actions from script requests
        p1 = bot_inst.parse_natural_bot_action("auto reconneti aç")
        self.assertIsNotNone(p1)
        self.assertEqual(p1["action"], "set_setting")
        self.assertEqual(p1["params"], {"key": "auto_reconnect", "value": True})

        p2 = bot_inst.parse_natural_bot_action("auto farmı kapat")
        self.assertIsNotNone(p2)
        self.assertEqual(p2["action"], "set_automation")
        self.assertEqual(p2["params"], {"automation": "auto_farm", "enabled": False})

        p3 = bot_inst.parse_natural_bot_action("START dünyasına git")
        self.assertIsNotNone(p3)
        self.assertEqual(p3["action"], "warp")
        self.assertEqual(p3["params"]["world"], "START")

        p4 = bot_inst.parse_natural_bot_action("botu bağla")
        self.assertIsNotNone(p4)
        self.assertEqual(p4["action"], "connect")

        self.assertIsNone(bot_inst.parse_natural_bot_action("auto reconnect açan lua scripti yaz"))
        self.assertIsNone(bot_inst.parse_natural_bot_action("auto reconnect nedir?"))

        # Register an owner-scoped bot and verify try_execute_natural_action dispatches directly
        test_owner = "998877665544332211"
        bot_key = "BerkimmmDirectTest"
        fleet_manager.update_heartbeat({
            "bot_name": bot_key,
            "owner_id": test_owner,
            "status": "retrieving_token",
            "raw_status": 34,
        })
        try:
            fleet_manager.pop_commands_for_bot(bot_key, owner_id=test_owner)
            mock_msg = MagicMock()
            mock_msg.author = MagicMock()
            mock_msg.author.id = int(test_owner)
            mock_msg.reply = AsyncMock()

            handled = await bot_inst.try_execute_natural_action(mock_msg, "auto reconneti aç", lang="tr")
            self.assertTrue(handled)
            mock_msg.reply.assert_awaited_once()
            reply_kwargs = mock_msg.reply.call_args.kwargs
            self.assertIsNone(reply_kwargs.get("file"))
            self.assertIn("Doğrudan Uygulandı", reply_kwargs["embed"].title)

            cmds = fleet_manager.pop_commands_for_bot(bot_key, owner_id=test_owner)
            actions = [c["action"] for c in cmds]
            self.assertIn("set_setting", actions)
            self.assertIn("run_script", actions)
            set_cmd = next(c for c in cmds if c["action"] == "set_setting")
            self.assertEqual(set_cmd["params"], {"key": "auto_reconnect", "value": True})
            lua_cmd = next(c for c in cmds if c["action"] == "run_script")
            self.assertIn("auto_reconnect = true", lua_cmd["params"]["code"])

            # Verify connect execution
            mock_msg.reply.reset_mock()
            handled_conn = await bot_inst.try_execute_natural_action(mock_msg, "botu bağla", lang="tr")
            self.assertTrue(handled_conn)
            cmds_conn = fleet_manager.pop_commands_for_bot(bot_key, owner_id=test_owner)
            self.assertEqual(cmds_conn[0]["action"], "connect")

            # Verify warp execution + ContextualActionView dynamic recent worlds
            mock_msg.reply.reset_mock()
            handled_warp = await bot_inst.try_execute_natural_action(mock_msg, "START dünyasına git", lang="tr")
            self.assertTrue(handled_warp)
            cmds_warp = fleet_manager.pop_commands_for_bot(bot_key, owner_id=test_owner)
            self.assertEqual(cmds_warp[0]["action"], "warp")
            self.assertEqual(cmds_warp[0]["params"]["world"], "START")
            warp_view = mock_msg.reply.call_args.kwargs.get("view")
            self.assertIsNotNone(warp_view)
            labels = [getattr(c, "label", "") for c in warp_view.children]
            self.assertIn("START", labels)

            # Verify "70 dirti dropla" resolves Dirt ID 2 directly (never buggy ID 70)
            p_drop = bot_inst.parse_natural_bot_action("70 dirti dropla")
            self.assertIsNotNone(p_drop)
            self.assertEqual(p_drop["action"], "drop")
            self.assertEqual(p_drop["params"]["item_id"], 2)
            self.assertEqual(p_drop["params"]["count"], 70)

            mock_msg.reply.reset_mock()
            handled_drop = await bot_inst.try_execute_natural_action(mock_msg, "70 dirti dropla", lang="tr")
            self.assertTrue(handled_drop)
            reply_drop_kw = mock_msg.reply.call_args.kwargs
            self.assertIsNone(reply_drop_kw.get("file"))
            cmds_drop = fleet_manager.pop_commands_for_bot(bot_key, owner_id=test_owner)
            self.assertEqual(cmds_drop[0]["action"], "drop")
            self.assertEqual(cmds_drop[0]["params"]["item_id"], 2)
            self.assertEqual(cmds_drop[0]["params"]["count"], 70)

            # Verify bot add natural command parsing
            p_add = bot_inst.parse_natural_bot_action("bot ekle YeniBot1 sifre123")
            self.assertIsNotNone(p_add)
            self.assertEqual(p_add["action"], "add_bot")
            self.assertEqual(p_add["params"]["name"], "YeniBot1")
            self.assertEqual(p_add["params"]["password"], "sifre123")
        finally:
            with fleet_manager._lock:
                fleet_manager._bots.pop(bot_key, None)
                fleet_manager._command_queues.pop(bot_key, None)
            try:
                await bot_inst.close()
            except Exception:
                pass


class TestV3FeaturesAndWebRelay(unittest.IsolatedAsyncioTestCase):
    def test_fuzzy_item_db_and_secret_key_lifecycle(self):
        from core.item_db import resolve_item_fuzzy

        dirt = resolve_item_fuzzy("dirti")
        self.assertIsNotNone(dirt)
        self.assertEqual(dirt["id"], 2)

        wl = resolve_item_fuzzy("wl")
        self.assertIsNotNone(wl)
        self.assertEqual(wl["id"], 242)

        with tempfile.TemporaryDirectory() as td:
            tm = TenantManager(storage_path=Path(td) / "tenants.json")
            sk = tm.get_or_create_secret_key("user_alpha", alias="Berk")
            self.assertTrue(sk.startswith("LUCI-"))
            self.assertEqual(tm.resolve_user_by_token(sk), "user_alpha")
            self.assertEqual(tm.resolve_user_by_token(sk.lower()), "user_alpha")
            tm.regenerate_token("user_alpha", alias="Berk")
            sk2 = tm.get_or_create_secret_key("user_alpha", alias="Berk")
            self.assertNotEqual(sk, sk2)
            self.assertIsNone(tm.resolve_user_by_token(sk))
            self.assertEqual(tm.resolve_user_by_token(sk2), "user_alpha")

    async def test_minimap_landmarks_and_bagla_secret_embed(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from core.minimap_renderer import extract_map_landmarks, render_minimap_bytes
        from discord_bot.bot import LuciferDiscordBot, MinimapControlView

        bot_inst = LuciferDiscordBot({"prefix": "!", "relay_url": "http://127.0.0.1:8829"})
        owner = "777666555444"
        bot_key = "MapCheckBot"
        # Place a Main Door (id 6) at (50, 23) and a Dirt (id 2) at (10, 10)
        rle = "0:2350,6:1"
        fleet_manager.update_heartbeat({
            "bot_name": bot_key,
            "owner_id": owner,
            "status": "online",
            "world": "ASDASDASDASD",
            "x": 50 * 32,
            "y": 23 * 32,
            "tiles": rle,
            "players": [{"name": "Friend1", "x": 15 * 32, "y": 20 * 32}],
        })
        try:
            bagla_emb = bot_inst._build_bagla_embed(owner_id=owner, alias="Berk", is_tr=True)
            full_text = (bagla_emb.description or "") + "\n".join(f.value for f in bagla_emb.fields)
            self.assertIn("LUCI-", full_text)
            self.assertIn("_G.LUCIFER_SECRET", full_text)

            lms = extract_map_landmarks(
                tiles=rle,
                bot_x=50 * 32,
                bot_y=23 * 32,
                other_players=[{"name": "Friend1", "x": 15 * 32, "y": 20 * 32}],
            )
            self.assertGreaterEqual(len(lms), 2)
            png = render_minimap_bytes(tiles=rle, bot_x=50 * 32, bot_y=23 * 32, world_name="TESTW", target_pos=(15, 20))
            self.assertTrue(png.startswith(b"\x89PNG"))

            mv = MinimapControlView(bot_inst, bot_name=bot_key, owner_id=owner)
            cids = [getattr(c, "custom_id", "") for c in mv.children]
            self.assertIn("sel_map_landmark", cids)
            self.assertIn("btn_map_coord_modal", cids)
        finally:
            with fleet_manager._lock:
                fleet_manager._bots.pop(bot_key, None)
                fleet_manager._command_queues.pop(bot_key, None)
            tenant_manager.delete_user(owner) if hasattr(tenant_manager, "delete_user") else None
            try:
                await bot_inst.close()
            except Exception:
                pass

    async def test_relay_web_map_detail_and_cmd_translation(self):
        relay = RelayServer()
        bot_key = "WebDeckUnit1"
        owner = "web_test_owner_01"
        fleet_manager.update_heartbeat({
            "bot_name": bot_key,
            "owner_id": owner,
            "status": "online",
            "world": "WEBWORLD",
            "x": 32 * 25,
            "y": 32 * 12,
            "tiles": "0:5999,2:1",
            "automations": {"auto_farm": False, "auto_collect": True, "auto_reconnect": True},
        })
        fleet_manager.pop_commands_for_bot(bot_key, owner_id=owner)

        try:
            async with TestClient(TestServer(relay.app)) as client:
                r_detail = await client.get(f"/api/bot/{bot_key}?owner_id={owner}")
                self.assertEqual(r_detail.status, 200)
                detail = await r_detail.json()
                self.assertEqual(detail["tile_x"], 25)
                self.assertEqual(detail["tile_y"], 12)
                self.assertIn("WEBWORLD", detail["recent_worlds"])
                self.assertIn("auto_reconnect", detail["automations"])

                r_map = await client.get(f"/api/bot/{bot_key}/map?owner_id={owner}&tx=12&ty=18")
                self.assertEqual(r_map.status, 200)
                self.assertEqual(r_map.headers.get("Content-Type"), "image/png")
                img_bytes = await r_map.read()
                self.assertTrue(img_bytes.startswith(b"\x89PNG"))

                r_mv = await client.post(f"/api/bot/{bot_key}/cmd?owner_id={owner}", json={"type": "move", "x": 12, "y": 18})
                self.assertEqual(r_mv.status, 200)
                j_mv = await r_mv.json()
                self.assertEqual(j_mv["action"], "find_path")

                r_go = await client.post(f"/api/bot/{bot_key}/cmd?owner_id={owner}", json={"type": "go", "world": "start"})
                self.assertEqual(r_go.status, 200)
                j_go = await r_go.json()
                self.assertEqual(j_go["action"], "warp")
                self.assertEqual(j_go["params"]["world"], "START")

                r_tgl = await client.post(f"/api/bot/{bot_key}/cmd?owner_id={owner}", json={"type": "toggle", "key": "farm"})
                self.assertEqual(r_tgl.status, 200)
                j_tgl = await r_tgl.json()
                self.assertEqual(j_tgl["action"], "set_automation")
                self.assertEqual(j_tgl["params"]["automation"], "auto_farm")
        finally:
            with fleet_manager._lock:
                fleet_manager._bots.pop(bot_key, None)
                fleet_manager._command_queues.pop(bot_key, None)


class BilingualAndLiveMapTests(unittest.IsolatedAsyncioTestCase):
    """Covers EN-default / TR-toggle UI, fleet inventory Q&A, Web Deck shelve, and 1:1 map rendering."""

    def test_tenant_lang_defaults_english_and_persists_turkish(self):
        from core.tenant_manager import tenant_manager

        uid = "lang_test_99182"
        with tenant_manager._lock:
            tenant_manager._users.pop(uid, None)

        self.assertEqual(tenant_manager.get_user_lang(uid), "en")
        self.assertEqual(tenant_manager.set_user_lang(uid, "tr", alias="LangTester"), "tr")
        self.assertEqual(tenant_manager.get_user_lang(uid), "tr")
        self.assertEqual(tenant_manager.set_user_lang(uid, "en"), "en")
        self.assertEqual(tenant_manager.get_user_lang(uid), "en")

        with tenant_manager._lock:
            tenant_manager._users.pop(uid, None)

    async def test_fleet_inventory_question_answers_directly_without_running_script(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from discord_bot.bot import LuciferDiscordBot

        owner = "q_owner_551"
        bot_key = "QueryBotOne"
        fleet_manager.update_heartbeat({
            "name": bot_key,
            "owner_id": owner,
            "world": "ASDASDABERKKK",
            "status": "online",
            "x": 67 * 32,
            "y": 23 * 32,
            "gem_count": 120,
            "inventory": [{"id": 2, "count": 70, "name": "Dirt"}],
        })

        class _Author:
            id = owner
            def __str__(self):
                return "brk"

        replies = []

        class _Message:
            author = _Author()
            guild = None
            content = "botlarda toplam kaç dirt var"

            async def reply(self, content=None, **kwargs):
                replies.append((content, kwargs))

        try:
            bot = LuciferDiscordBot({"prefix": "!"})
            self.assertFalse(bot.is_direct_execution_intent("botlarda toplam kaç dirt var"))
            self.assertFalse(bot.is_direct_execution_intent("how many dirt do my bots have?"))
            self.assertTrue(bot.is_direct_execution_intent("70 dirti dropla"))

            fleet_manager.pop_commands_for_bot(bot_key, owner_id=owner)
            handled = await bot.try_answer_fleet_query(_Message(), "botlarda toplam kaç dirt var", lang="tr")
            self.assertTrue(handled)
            self.assertEqual(len(replies), 1)
            emb = replies[0][1]["embed"]
            self.assertIn("70", emb.description)
            self.assertIn("Dirt", emb.title)
            self.assertEqual(fleet_manager.pop_commands_for_bot(bot_key, owner_id=owner), [])
        finally:
            with fleet_manager._lock:
                fleet_manager._bots.pop(bot_key, None)
                fleet_manager._command_queues.pop(bot_key, None)

    async def test_english_default_views_and_turkish_switch(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from discord_bot.bot import (
            BaglaControlView,
            ContextualActionView,
            FleetControlView,
            HelpDashboardView,
            LuciferDiscordBot,
            MinimapControlView,
        )

        owner = "ui_lang_owner_772"
        bot_key = "UiLangBot"
        fleet_manager.update_heartbeat({
            "name": bot_key,
            "owner_id": owner,
            "world": "START",
            "world_public": False,
            "status": "online",
            "x": 1600,
            "y": 736,
            "tiles": "14:2400,2:3599,242:1",
        })
        try:
            bot = LuciferDiscordBot({"prefix": "!"})
            status_en = bot.build_status_embed(owner_id=owner)
            self.assertIn("Fleet Status", status_en.title)

            fleet_en = FleetControlView(bot, owner_id=owner)
            labels_en = [getattr(c, "label", "") for c in fleet_en.children]
            self.assertIn("Refresh", labels_en)
            self.assertIn("Connect", labels_en)
            self.assertIn("Türkçe", labels_en)

            map_en = MinimapControlView(bot, bot_name=bot_key, owner_id=owner)
            map_labels_en = [getattr(c, "label", "") for c in map_en.children]
            self.assertIn("Coords & Command", map_labels_en)
            self.assertIn("Walk Here", map_labels_en)

            help_en = HelpDashboardView(bot, owner_id=owner)
            self.assertIn("Fleet Status (DM)", [getattr(c, "label", "") for c in help_en.children])

            ctx_en = ContextualActionView(bot, category="world", owner_id=owner)
            self.assertIn("Enter Door", [getattr(c, "label", "") for c in ctx_en.children])

            bagla_en = BaglaControlView(bot, owner_id=owner)
            self.assertIn("Regenerate Key", [getattr(c, "label", "") for c in bagla_en.children])

            fleet_tr = FleetControlView(bot, owner_id=owner, lang="tr")
            labels_tr = [getattr(c, "label", "") for c in fleet_tr.children]
            self.assertIn("Yenile", labels_tr)
            self.assertIn("Oyuna Sok", labels_tr)
            self.assertIn("English", labels_tr)
        finally:
            with fleet_manager._lock:
                fleet_manager._bots.pop(bot_key, None)
                fleet_manager._command_queues.pop(bot_key, None)

    async def test_web_deck_shelved_and_sky_contour_minimap(self):
        from aiohttp.test_utils import TestClient, TestServer
        from PIL import Image
        import io
        from core.minimap_renderer import COLOR_CONTOUR, COLOR_SKY, render_minimap_bytes
        from core.relay_server import RelayServer

        relay = RelayServer()
        async with TestClient(TestServer(relay.app)) as client:
            r = await client.get("/")
            self.assertEqual(r.status, 200)
            body = await r.text()
            self.assertIn("disabled", body.lower())

        # Tile row 0 has sky (14), row 1 has solid Dirt (2): boundary pixel renders crisp contour color.
        rle = "14:100,2:100,0:5799,242:1"
        png_bytes = render_minimap_bytes(tiles=rle, world_name="LOCKEDW", is_public=True, lang="en")
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (544, 389))
        # Row 0 sky tile interior (MAP_OFFSET_Y=62, TILE_PIXEL_SIZE=5)
        self.assertEqual(img.getpixel((50, 64)), COLOR_SKY)
        # Row 1 dirt tile top edge should render dark contour outline against sky row above
        self.assertEqual(img.getpixel((50, 67)), COLOR_CONTOUR)

    async def test_strict_mention_gate_ignores_untagged_and_other_user_mentions(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from types import SimpleNamespace
        from discord_bot.bot import LuciferDiscordBot

        bot = LuciferDiscordBot({"prefix": "!", "ai_channel_id": 77777})
        bot_user = SimpleNamespace(id=888888, name="Prometheus AI")
        other_user = SimpleNamespace(id=999999, name="OtherUser")
        bot._connection.user = bot_user
        bot.process_commands = AsyncMock()
        bot.sync_relay_fleet = AsyncMock()

        def _make_msg(content: str, guild=None, channel_id=77777, mentions=None):
            msg = MagicMock()
            msg.author = SimpleNamespace(id=1234567, bot=False)
            msg.content = content
            msg.guild = guild
            msg.channel = SimpleNamespace(id=channel_id, typing=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
            msg.mentions = mentions or []
            msg.role_mentions = []
            msg.reference = None
            msg.reply = AsyncMock()
            return msg

        with patch("discord_bot.bot.evren_client.chat", AsyncMock(return_value={"text": "ok", "code": "", "slug": ""})) as mock_chat:
            # 1. Untagged message in ai_channel_id -> must do nothing
            m_ai = _make_msg("START dünyasına git", guild=SimpleNamespace(id=1, me=None), channel_id=77777, mentions=[])
            await bot.on_message(m_ai)
            m_ai.reply.assert_not_called()

            # 2. Untagged message in DM -> must do nothing
            m_dm = _make_msg("door massı yapmak istiyorum", guild=None, channel_id=55555, mentions=[])
            await bot.on_message(m_dm)
            m_dm.reply.assert_not_called()

            # 3. Tagging another user -> must do nothing
            m_other = _make_msg("<@999999> door massı yapmak istiyorum", guild=SimpleNamespace(id=1, me=None), channel_id=77777, mentions=[other_user])
            await bot.on_message(m_other)
            m_other.reply.assert_not_called()
            mock_chat.assert_not_called()

            # 4. Explicit mention of bot -> responds!
            m_bot = _make_msg("<@888888> merhaba", guild=SimpleNamespace(id=1, me=None), channel_id=77777, mentions=[bot_user])
            with patch("discord_bot.bot.quota_manager.check_and_consume", return_value=(True, "", 9)):
                await bot.on_message(m_bot)
            mock_chat.assert_awaited_once()
            m_bot.reply.assert_called_once()
            self.assertNotIn("file", m_bot.reply.call_args.kwargs)

    async def test_door_mass_wiki_and_live_inventory_response(self):
        from types import SimpleNamespace
        from core.item_db import get_mass_plan, get_splicing_recipe
        from core.tenant_manager import tenant_manager

        door_rec = get_splicing_recipe("Door")
        self.assertIsNotNone(door_rec)
        self.assertEqual(int(door_rec["item_id"]), 12)
        ing_sids = {int(i["seed_id"]) for i in door_rec["ingredients"]}
        self.assertEqual(ing_sids, {3, 15})  # Dirt Seed (3) + Cave Background Seed (15)

        plan = get_mass_plan("door massı yapmak istiyorumda hangi seedlerden lazım ve envanterimde olan seedler varmı?")
        self.assertIsNotNone(plan)
        self.assertEqual(int(plan["target"]["item_id"]), 12)

        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from discord_bot.bot import LuciferDiscordBot

        owner = "777888999"
        bot_key = "MassSeedBot"
        tenant_manager.set_user_lang(owner, "tr", alias="BerkTest")
        fleet_manager.update_heartbeat({
            "name": bot_key,
            "owner_id": owner,
            "world": "ASDASDABERKKK",
            "status": "online",
            "x": 1600,
            "y": 736,
            "inventory": [
                {"id": 3, "count": 45},
                {"id": 5, "count": 12},
                {"id": 15, "count": 20},
                {"id": 2, "count": 200},
            ],
        })
        try:
            bot = LuciferDiscordBot({"prefix": "!"})
            bot_user = SimpleNamespace(id=888888, name="Prometheus AI")
            bot._connection.user = bot_user
            bot.process_commands = AsyncMock()
            bot.sync_relay_fleet = AsyncMock()

            msg = MagicMock()
            msg.author = SimpleNamespace(id=int(owner), bot=False)
            msg.content = "<@888888> door massı yapmak istiyorumda hangi seedlerden lazım ve envanterimde olan seedler varmı?"
            msg.guild = None
            msg.channel = SimpleNamespace(id=55555)
            msg.mentions = [bot_user]
            msg.role_mentions = []
            msg.reference = None
            msg.reply = AsyncMock()

            with patch("discord_bot.bot.evren_client.chat", AsyncMock()) as mock_chat:
                await bot.on_message(msg)
                mock_chat.assert_not_called()

            msg.reply.assert_called_once()
            kwargs = msg.reply.call_args.kwargs
            self.assertNotIn("file", kwargs)
            embed = kwargs["embed"]
            full_text = f"{embed.title}\n{embed.description}\n" + "\n".join(f"{f.name}\n{f.value}" for f in embed.fields)
            self.assertIn("Dirt Seed", full_text)
            self.assertIn("Cave Background Seed", full_text)
            self.assertIn("45", full_text)
            self.assertIn("20", full_text)
            self.assertIn("Lava Seed", full_text)
            self.assertIn("12", full_text)
        finally:
            with fleet_manager._lock:
                fleet_manager._bots.pop(bot_key, None)
                fleet_manager._command_queues.pop(bot_key, None)

    async def test_deduplicate_and_language_slash_command(self):
        from types import SimpleNamespace
        from core.evren_client import _deduplicate_repetitive_paragraphs
        from core.tenant_manager import tenant_manager

        rep = (
            "Door yapmak için Dirt Seed (ID: 3) ve Cave Background Seed (ID: 15) birleştirilir.\n\n"
            "```lua\nlocal a = 1\n```\n\n"
            "Door yapmak için Dirt Seed (ID: 3) ve Cave Background Seed (ID: 15) birleştirilir.\n\n"
            "Ekstra olarak Lava Seed kontrol edildi."
        )
        deduped = _deduplicate_repetitive_paragraphs(rep)
        self.assertEqual(deduped.count("Dirt Seed (ID: 3) ve Cave Background Seed (ID: 15)"), 1)
        self.assertIn("```lua\nlocal a = 1\n```", deduped)
        self.assertIn("Ekstra olarak Lava Seed kontrol edildi.", deduped)

        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        import discord
        from discord_bot.bot import LuciferDiscordBot

        bot = LuciferDiscordBot({"prefix": "!"})
        await bot.register_slash_commands()
        lang_cmd = bot.tree.get_command("language")
        self.assertIsNotNone(lang_cmd, "/language slash command must be registered")

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = SimpleNamespace(id=55667788)
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await lang_cmd.callback(interaction, language="en")
        self.assertEqual(tenant_manager.get_user_lang("55667788"), "en")
        await lang_cmd.callback(interaction, language="tr")
        self.assertEqual(tenant_manager.get_user_lang("55667788"), "tr")

    async def test_three_subscription_roles_pricing_and_quotas(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from types import SimpleNamespace
        from discord_bot.bot import LuciferDiscordBot
        from discord_bot.priority_queue import PRIORITY_VIP, resolve_user_priority
        from discord_bot.quota_manager import TIER_CONFIG, quota_manager

        for role_key, exp_limit, exp_cd, exp_bots in (
            ("starter", 40, 20, 5),
            ("vip", 120, 10, 25),
            ("elite", 500, 3, 100),
        ):
            cfg = TIER_CONFIG.get(role_key)
            self.assertIsNotNone(cfg)
            self.assertEqual(cfg["daily_limit"], exp_limit)
            self.assertEqual(cfg["cooldown_seconds"], exp_cd)
            self.assertEqual(cfg["max_bots"], exp_bots)
            self.assertTrue(cfg.get("price_tr"))
            self.assertTrue(cfg.get("price_en"))

        test_uid = 9988776611
        with patch.object(quota_manager, "save", lambda: None):
            try:
                self.assertTrue(quota_manager.set_tier(test_uid, "bronze"))
                self.assertEqual(quota_manager.get_status(test_uid)["tier"], "starter")
                self.assertEqual(quota_manager.get_status(test_uid)["max_bots"], 5)

                self.assertTrue(quota_manager.set_tier(test_uid, "pro"))
                self.assertEqual(quota_manager.get_status(test_uid)["tier"], "vip")
                self.assertEqual(quota_manager.get_status(test_uid)["max_bots"], 25)

                self.assertTrue(quota_manager.set_tier(test_uid, "ultra"))
                self.assertEqual(quota_manager.get_status(test_uid)["tier"], "elite")
                self.assertEqual(quota_manager.get_status(test_uid)["max_bots"], 100)
                self.assertEqual(resolve_user_priority(None, user_id=test_uid)[0], PRIORITY_VIP)

                elite_member = SimpleNamespace(
                    guild_permissions=SimpleNamespace(administrator=False),
                    guild=None,
                    roles=[SimpleNamespace(name="Elite / Ultra")],
                )
                self.assertEqual(quota_manager.sync_member_role_tier(elite_member, test_uid), "elite")

                bot = LuciferDiscordBot({"prefix": "!"})
                bot.register_prefix_commands()
                await bot.register_slash_commands()
                self.assertIsNotNone(bot.get_command("roller"))
                self.assertIsNotNone(bot.tree.get_command("roles"))
                self.assertIsNotNone(bot.tree.get_command("pricing"))

                emb_tr = bot.build_roles_pricing_embed(user_id=test_uid, lang="tr")
                text_tr = f"{emb_tr.title}\n{emb_tr.description}\n" + "\n".join(f"{f.name}\n{f.value}" for f in emb_tr.fields)
                self.assertIn("Starter", text_tr)
                self.assertIn("VIP", text_tr)
                self.assertIn("Elite", text_tr)
                self.assertIn("₺99", text_tr)
                self.assertIn("₺249", text_tr)
                self.assertIn("₺499", text_tr)

                emb_en = bot.build_roles_pricing_embed(user_id=test_uid, lang="en")
                text_en = f"{emb_en.title}\n{emb_en.description}\n" + "\n".join(f"{f.name}\n{f.value}" for f in emb_en.fields)
                self.assertIn("$3", text_en)
                self.assertIn("$7.50", text_en)
                self.assertIn("$15", text_en)
                self.assertIn("500", text_en)
            finally:
                quota_manager._data.pop(str(test_uid), None)


if __name__ == "__main__":
    unittest.main()
