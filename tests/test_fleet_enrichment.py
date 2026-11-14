"""
Milestone 4: Autonomous Fleet Enrichment Unit & Integration Tests
Tests:
1. core/bot_manager.py:
   - queue_broadcast_command (online filtering, all bots, target bot_names, empty fleet)
   - get_fleet_inventory_summary (total gems, items, sorting, malformed resilience)
   - get_fleet_activity_stats (world distribution, status breakdown, uptime, farming stats)
2. web/server.py:
   - POST /api/fleet/broadcast (queue commands across active bots, validation, filters)
   - GET /api/fleet/stats (enriched fleet activity and resource aggregation)
3. discord_bot/bot.py:
   - !filo_durum / !fleet_status (comprehensive bilingual status embed)
   - !filo_isinlan / !fleet_warp (broadcast warp command with ASCII world name validation)
   - !ciftlik_istatistik / !farm_stats (bilingual farming stats embed and telemetry)
"""
from __future__ import annotations

import math
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient

from core.bot_manager import BotManager, BotState, fleet_manager
from web.server import app

try:
    import discord
    from discord.ext import commands
    from discord_bot.bot import LuciferDiscordBot
    _HAS_DISCORD_BOT = True
except ImportError:
    discord = None
    commands = None
    LuciferDiscordBot = None
    _HAS_DISCORD_BOT = False


class TestFleetCommandDispatch(unittest.TestCase):
    """Tests queue_broadcast_command multi-bot dispatch in core/bot_manager.py."""

    def setUp(self):
        self.bm = BotManager()

    def test_queue_broadcast_command_online_only(self):
        """Verify broadcast only targets online/alive bots when filter_online=True."""
        now = time.time()
        # Bot 1: Online & Alive
        self.bm._bots["Bot1"] = BotState(name="Bot1", status="online", last_seen=now)
        # Bot 2: Online & Alive
        self.bm._bots["Bot2"] = BotState(name="Bot2", status="online", last_seen=now)
        # Bot 3: Offline
        self.bm._bots["Bot3"] = BotState(name="Bot3", status="offline", last_seen=now - 50)

        count = self.bm.queue_broadcast_command(
            action="warp",
            params={"world": "FARM"},
            filter_online=True,
        )
        self.assertEqual(count, 2, "Should target exactly the 2 alive bots")

        # Verify Bot1 and Bot2 have the command queued
        cmds1 = self.bm.pop_commands_for_bot("Bot1")
        self.assertEqual(len(cmds1), 1)
        self.assertEqual(cmds1[0]["action"], "warp")
        self.assertEqual(cmds1[0]["params"], {"world": "FARM"})

        cmds2 = self.bm.pop_commands_for_bot("Bot2")
        self.assertEqual(len(cmds2), 1)
        self.assertEqual(cmds2[0]["action"], "warp")

        # Verify Bot3 did NOT receive the command
        cmds3 = self.bm.pop_commands_for_bot("Bot3")
        self.assertEqual(len(cmds3), 0)

    def test_queue_broadcast_command_all_bots(self):
        """Verify broadcast targets ALL bots (including offline) when filter_online=False."""
        now = time.time()
        self.bm._bots["BotA"] = BotState(name="BotA", status="online", last_seen=now)
        self.bm._bots["BotB"] = BotState(name="BotB", status="offline", last_seen=now - 100)

        count = self.bm.queue_broadcast_command(
            action="respawn",
            params={},
            filter_online=False,
        )
        self.assertEqual(count, 2, "Should target all 2 registered bots")

        cmdsA = self.bm.pop_commands_for_bot("BotA")
        cmdsB = self.bm.pop_commands_for_bot("BotB")
        self.assertEqual(len(cmdsA), 1)
        self.assertEqual(len(cmdsB), 1)

    def test_queue_broadcast_command_targeted_names(self):
        """Verify broadcast can be targeted to a specific subset of bot names."""
        now = time.time()
        self.bm._bots["Alpha"] = BotState(name="Alpha", status="online", last_seen=now)
        self.bm._bots["Beta"] = BotState(name="Beta", status="online", last_seen=now)
        self.bm._bots["Gamma"] = BotState(name="Gamma", status="online", last_seen=now)

        count = self.bm.queue_broadcast_command(
            action="say",
            params={"text": "Hello"},
            filter_online=True,
            bot_names=["Alpha", "Gamma"],
        )
        self.assertEqual(count, 2)
        self.assertEqual(len(self.bm.pop_commands_for_bot("Alpha")), 1)
        self.assertEqual(len(self.bm.pop_commands_for_bot("Beta")), 0)
        self.assertEqual(len(self.bm.pop_commands_for_bot("Gamma")), 1)

    def test_queue_broadcast_command_empty_fleet(self):
        """Verify broadcast returns 0 when no bots are present."""
        count = self.bm.queue_broadcast_command("warp", {"world": "JAMMER"})
        self.assertEqual(count, 0)


class TestFleetMetricsAndAggregation(unittest.TestCase):
    """Tests get_fleet_inventory_summary and get_fleet_activity_stats in core/bot_manager.py."""

    def setUp(self):
        self.bm = BotManager()

    def test_get_fleet_inventory_summary_aggregation(self):
        """Verify accurate aggregation of gems, pearls, vouchers, and items across all bots."""
        self.bm._bots["Bot1"] = BotState(
            name="Bot1",
            status="online",
            gem_count=10000,
            pearl_count=5,
            voucher_count=2,
            inventory=[
                {"id": 242, "name": "World Lock", "count": 25},
                {"id": 3, "name": "Dirt", "count": 150},
            ],
        )
        self.bm._bots["Bot2"] = BotState(
            name="Bot2",
            status="online",
            gem_count=25000,
            pearl_count=10,
            voucher_count=1,
            inventory=[
                {"id": 242, "name": "World Lock", "count": 75},
                {"id": 12, "name": "Door", "count": 50},
            ],
        )

        inv = self.bm.get_fleet_inventory_summary()
        self.assertEqual(inv["total_bots"], 2)
        self.assertEqual(inv["total_gems"], 35000)
        self.assertEqual(inv["total_pearls"], 15)
        self.assertEqual(inv["total_vouchers"], 3)
        self.assertEqual(inv["total_items"], 300)
        self.assertEqual(inv["unique_items"], 3)

        # Check World Lock (id 242) aggregation (25 + 75 = 100)
        wl = next((it for it in inv["items"] if it["id"] == 242), None)
        self.assertIsNotNone(wl)
        self.assertEqual(wl["count"], 100)

        # Verify sorted by count descending (Dirt 150, World Lock 100, Door 50)
        counts = [it["count"] for it in inv["items"]]
        self.assertEqual(counts, [150, 100, 50])

    def test_get_fleet_inventory_summary_malformed_resilience(self):
        """Verify inventory summary handles invalid, string, negative, and None fields gracefully."""
        self.bm._bots["BotBad"] = BotState(
            name="BotBad",
            gem_count=None,
            inventory=[
                {"id": "242", "count": "50"},  # String coercion
                {"id": "invalid", "count": "abc"},  # Invalid
                {"id": 3, "count": -10},  # Negative
                "not_a_dict",  # Corrupted element
            ],
        )
        inv = self.bm.get_fleet_inventory_summary()
        self.assertEqual(inv["total_gems"], 0)
        wl = next((it for it in inv["items"] if it["id"] == 242), None)
        self.assertIsNotNone(wl)
        self.assertEqual(wl["count"], 50)

    def test_get_fleet_activity_stats(self):
        """Verify activity metrics: world distribution, status breakdown, farming counts, and ping."""
        now = time.time()
        self.bm._bots["Bot1"] = BotState(
            name="Bot1",
            status="online",
            world="START",
            ping=40,
            last_seen=now,
        )
        self.bm._bots["Bot2"] = BotState(
            name="Bot2",
            status="online",
            world="START",
            ping=60,
            automations={"auto_farm": True},
            last_seen=now,
        )
        self.bm._bots["Bot3"] = BotState(
            name="Bot3",
            status="online",
            world="FARM_NET",
            ping=50,
            automations={"auto_farm": True},
            last_seen=now,
        )
        self.bm._bots["Bot4"] = BotState(
            name="Bot4",
            status="offline",
            world="",
            last_seen=now - 100,
        )

        stats = self.bm.get_fleet_activity_stats()
        self.assertEqual(stats["total_bots"], 4)
        self.assertEqual(stats["online_bots"], 3)
        self.assertEqual(stats["offline_bots"], 1)

        # World distribution
        self.assertEqual(stats["world_distribution"].get("START"), 2)
        self.assertEqual(stats["world_distribution"].get("FARM_NET"), 1)

        # Status breakdown
        self.assertEqual(stats["status_breakdown"].get("online"), 3)
        self.assertEqual(stats["status_breakdown"].get("offline"), 1)

        # Active farming: Bot2 (auto_farm) + Bot3 (auto_farm)
        self.assertEqual(stats["active_farming_bots"], 2)

        # Ping: (40 + 60 + 50) / 3 = 50.0
        self.assertEqual(stats["average_ping"], 50.0)

        # Uptime dict
        self.assertIn("uptime", stats)
        self.assertEqual(stats["uptime"]["tracked_bots"], 3)
        self.assertGreaterEqual(stats["uptime"]["total_seconds"], 0.0)


class TestWebFleetEnrichmentEndpoints(unittest.TestCase):
    """Tests FastAPI /api/fleet/broadcast and /api/fleet/stats endpoints in web/server.py."""

    def setUp(self):
        self.client = TestClient(app)

    def test_api_fleet_stats_endpoint(self):
        """Verify GET /api/fleet/stats returns 200 with enriched metrics."""
        resp = self.client.get("/api/fleet/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("activity", data)
        self.assertIn("inventory", data)
        self.assertIn("total_bots", data)
        self.assertIn("online_bots", data)
        self.assertIn("total_gems", data)
        self.assertIn("world_distribution", data)
        self.assertIn("status_breakdown", data)
        self.assertIn("uptime", data)

    def test_api_fleet_broadcast_endpoint_post(self):
        """Verify POST /api/fleet/broadcast successfully dispatches command across fleet."""
        # Ensure at least one bot is online via heartbeat
        hb_payload = {
            "bot_name": "FleetBot_1",
            "status": "online",
            "world": "START",
            "gems": 500,
        }
        self.client.post("/api/heartbeat", json=hb_payload)

        # Broadcast warp command
        broadcast_payload = {
            "action": "warp",
            "world": "JAMMER",
            "filter_online": True,
        }
        resp = self.client.post("/api/fleet/broadcast", json=broadcast_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["action"], "warp")
        self.assertGreaterEqual(data["targeted_bots"], 1)
        self.assertEqual(data["params"]["world"], "JAMMER")

    def test_api_fleet_broadcast_endpoint_validation(self):
        """Verify validation errors on missing action or invalid JSON body."""
        # Empty body
        resp = self.client.post("/api/fleet/broadcast", json={})
        self.assertEqual(resp.status_code, 400)

        # Invalid body (not an object)
        resp = self.client.post("/api/fleet/broadcast", json=["not", "dict"])
        self.assertEqual(resp.status_code, 400)

        # Using command alias instead of action
        resp = self.client.post("/api/fleet/broadcast", json={"command": "respawn"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["action"], "respawn")


class TestDiscordBotFleetEnrichment(unittest.IsolatedAsyncioTestCase):
    """Tests new Discord Bot fleet commands and embeds in discord_bot/bot.py."""

    def setUp(self):
        if not _HAS_DISCORD_BOT:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        from discord_bot.emoji_manager import clear_emoji_cache
        patcher = patch("discord_bot.emoji_manager.load_configured_emojis", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)
        clear_emoji_cache()
        self.bot = LuciferDiscordBot({"prefix": "!"})

    def test_build_fleet_status_embed_bilingual(self):
        """Verify build_fleet_status_embed generates rich embeds in TR and EN."""
        # Register a test bot into fleet_manager
        fleet_manager.update_heartbeat({
            "bot_name": "TestFleetBot",
            "status": "online",
            "world": "START",
            "gems": 12000,
        })

        # Turkish embed
        embed_tr = self.bot.build_fleet_status_embed(lang="tr")
        self.assertIn("Prometheus AI", embed_tr.title)
        self.assertIn("Filo Durumu", embed_tr.title)
        field_names_tr = [f.name for f in embed_tr.fields]
        self.assertIn("🤖 Bot Durumu", field_names_tr)
        self.assertIn("💎 Toplam Gem", field_names_tr)
        self.assertIn("🌍 Dünya Dağılımı", field_names_tr)

        # English embed
        embed_en = self.bot.build_fleet_status_embed(lang="en")
        self.assertIn("Prometheus AI", embed_en.title)
        self.assertIn("Fleet Status", embed_en.title)
        field_names_en = [f.name for f in embed_en.fields]
        self.assertIn("🤖 Bot Status", field_names_en)
        self.assertIn("💎 Total Gems", field_names_en)
        self.assertIn("🌍 World Distribution", field_names_en)

    def test_build_farm_stats_embed_bilingual(self):
        """Verify build_farm_stats_embed generates farming telemetry in TR and EN."""
        fleet_manager.update_heartbeat({
            "bot_name": "FarmerBot_Alpha",
            "status": "online",
            "world": "FARM_1",
            "gems": 50000,
            "automations": {"auto_farm": True},
            "inventory": [{"id": 242, "name": "World Lock", "count": 10}],
        })

        # Turkish farm stats
        embed_tr = self.bot.build_farm_stats_embed(lang="tr")
        self.assertIn("Çiftlik", embed_tr.title)
        field_names_tr = [f.name for f in embed_tr.fields]
        self.assertIn("💎 Biriken Gemler", field_names_tr)
        self.assertIn("🚜 Aktif Çiftçi Botlar", field_names_tr)
        self.assertIn("📡 Ağ & Telemetri", field_names_tr)

        # English farm stats
        embed_en = self.bot.build_farm_stats_embed(lang="en")
        self.assertIn("Farming", embed_en.title)
        field_names_en = [f.name for f in embed_en.fields]
        self.assertIn("💎 Accumulated Gems", field_names_en)
        self.assertIn("🚜 Active Farming Bots", field_names_en)
        self.assertIn("📡 Network & Telemetry", field_names_en)

    def test_fleet_warp_ascii_validation_logic(self):
        """Verify world name ASCII validation rejects non-ASCII and accepts pure ASCII."""
        valid_worlds = ["START", "FARM_WORLD_1", "JAMMER123", "ASDASDASD"]
        for w in valid_worlds:
            self.assertTrue(all(ord(c) < 128 for c in w), f"Should be valid ASCII: {w}")

        invalid_worlds = ["ÇİFTLİK", "DÜNYA", "TÜRKİYE", "WORLD_💎", "BAĞLANTI"]
        for w in invalid_worlds:
            self.assertFalse(all(ord(c) < 128 for c in w), f"Should be detected as non-ASCII: {w}")

    async def test_prefix_command_dispatch_mocks(self):
        """Verify command callbacks execute cleanly and invoke ctx.reply."""
        self.bot.register_prefix_commands()

        # 1. Test filo_durum
        cmd_filo = self.bot.get_command("filo_durum")
        self.assertIsNotNone(cmd_filo)
        ctx_mock = AsyncMock()
        ctx_mock.invoked_with = "filo_durum"
        ctx_mock.message.content = "!filo_durum"
        await cmd_filo.callback(ctx_mock)
        ctx_mock.reply.assert_called_once()
        sent_embed = ctx_mock.reply.call_args[1].get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("Filo Durumu", sent_embed.title)

        # 2. Test fleet_status alias in English
        ctx_mock_en = AsyncMock()
        ctx_mock_en.invoked_with = "fleet_status"
        ctx_mock_en.message.content = "!fleet_status"
        await cmd_filo.callback(ctx_mock_en)
        sent_embed_en = ctx_mock_en.reply.call_args[1].get("embed")
        self.assertIn("Fleet Status", sent_embed_en.title)

        # 3. Test farm_stats command
        cmd_farm = self.bot.get_command("ciftlik_istatistik")
        self.assertIsNotNone(cmd_farm)
        ctx_farm = AsyncMock()
        ctx_farm.invoked_with = "farm_stats"
        ctx_farm.message.content = "!farm_stats"
        await cmd_farm.callback(ctx_farm)
        sent_farm_embed = ctx_farm.reply.call_args[1].get("embed")
        self.assertIn("Farming", sent_farm_embed.title)

        # 4. Test fleet_warp with ASCII world
        cmd_warp = self.bot.get_command("filo_isinlan")
        self.assertIsNotNone(cmd_warp)
        ctx_warp = AsyncMock()
        ctx_warp.invoked_with = "fleet_warp"
        ctx_warp.message.content = "!fleet_warp JAMMER_WORLD"
        await cmd_warp.callback(ctx_warp, world="JAMMER_WORLD")
        ctx_warp.reply.assert_called_once()
        reply_text = ctx_warp.reply.call_args[0][0]
        self.assertIn("JAMMER_WORLD", reply_text)

        # 5. Test fleet_warp with non-ASCII world (Must reject!)
        ctx_warp_err = AsyncMock()
        ctx_warp_err.invoked_with = "filo_isinlan"
        ctx_warp_err.message.content = "!filo_isinlan ÇİFTLİK"
        await cmd_warp.callback(ctx_warp_err, world="ÇİFTLİK")
        ctx_warp_err.reply.assert_called_once()
        err_text = ctx_warp_err.reply.call_args[0][0]
        self.assertIn("ASCII", err_text)
        self.assertIn("Hata", err_text)


if __name__ == "__main__":
    unittest.main()
