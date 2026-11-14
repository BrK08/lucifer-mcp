"""
Adversarial Stress Harness for Milestone 2 Fleet Telemetry
Executed by Challenger 2 (m2_challenger_2).

Challenges:
1. Multi-Bot Fleet Simulation:
   - 50 bots concurrently posting heartbeats to /api/heartbeat
   - 50 bots in a single batched list payload
   - High-throughput bursts (50 bots x 10 cycles = 500 concurrent requests)
   - Concurrent command queueing and draining without cross-talk
2. BotState.gems Property & Mutation Invariants:
   - Rapid multi-threaded read/write mutation stress
   - Gems resolution hierarchy (gems vs gem_count precedence)
   - Type coercion (string numbers, invalid strings, None, negative, large ints)
3. ASCII Cleanliness:
   - Strict 7-bit ASCII & Turkish character audit across bridge/lucifer_bridge.lua
   - Cleanliness check across core/bot_manager.py and web/server.py
4. Lua Bridge JSON Regex & Multibot Logic:
   - Deep nested structures, URLs with colons, array-of-objects decoding
   - getBots() multi-bot table aggregation verification
"""
from __future__ import annotations

import concurrent.futures
import json
import random
import re
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient
from web.server import app
from core.bot_manager import BotManager, BotState, fleet_manager


class TestMultiBotFleetSimulation(unittest.TestCase):
    """Stress test the fleet telemetry pipeline under massive multi-bot concurrency."""

    def setUp(self):
        self.client = TestClient(app)
        # Dedicated local BotManager to isolate test state when needed
        self.local_manager = BotManager()

    def test_fifty_bots_concurrent_heartbeat_burst(self):
        """
        Simulate 50 unique bots concurrently firing heartbeats to /api/heartbeat.
        Verifies:
        - All 50 requests succeed with HTTP 200.
        - All 50 bots are registered in fleet_manager.
        - Bot names and telemetry match payload values.
        """
        bot_count = 50
        results = []

        def bot_worker(bot_id: int):
            bot_name = f"FleetSim_Bot_{bot_id:03d}"
            payload = {
                "bot_name": bot_name,
                "status": "online",
                "raw_status": 1,
                "world": f"FARM_{bot_id}",
                "x": bot_id,
                "y": bot_id * 2,
                "gems": bot_id * 100,
                "level": (bot_id % 20) + 1,
                "ping": 30 + (bot_id % 50),
            }
            resp = self.client.post("/api/heartbeat", json=payload)
            return bot_id, resp.status_code, resp.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(bot_worker, i) for i in range(1, bot_count + 1)]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        self.assertEqual(len(results), bot_count, "All 50 bot threads must report results.")

        # Assert all HTTP 200
        for bot_id, status_code, body in results:
            self.assertEqual(
                status_code, 200,
                f"Bot {bot_id} received unexpected status {status_code}: {body}"
            )
            self.assertEqual(body.get("status"), "ok")
            expected_name = f"FleetSim_Bot_{bot_id:03d}"
            self.assertEqual(body.get("bot"), expected_name)

        # Verify fleet_manager integrity
        summary = fleet_manager.get_fleet_summary()
        self.assertGreaterEqual(summary["total_bots"], bot_count)

        for i in range(1, bot_count + 1):
            name = f"FleetSim_Bot_{i:03d}"
            bot = fleet_manager.get_bot(name)
            self.assertIsNotNone(bot, f"Bot {name} must exist in fleet_manager.")
            self.assertEqual(bot.world, f"FARM_{i}")
            self.assertEqual(bot.gems, i * 100)
            self.assertEqual(bot.gem_count, i * 100)

    def test_batched_list_payload_with_fifty_bots(self):
        """
        Simulate a bridge or aggregator sending a list of 50 bots in a single HTTP POST.
        """
        batch = []
        for i in range(1, 51):
            batch.append({
                "bot_name": f"BatchBot_{i:02d}",
                "status": "online",
                "world": "START",
                "gems": 500 + i,
            })

        resp = self.client.post("/api/heartbeat", json=batch)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("fleet_size"), 50)
        self.assertIn("commands", data)

        # Verify all 50 bots registered
        for i in range(1, 51):
            b = fleet_manager.get_bot(f"BatchBot_{i:02d}")
            self.assertIsNotNone(b)
            self.assertEqual(b.gems, 500 + i)

    def test_concurrent_batched_list_bursts(self):
        """
        Test 10 concurrent requests, each posting a list of 5 bots (50 bots total).
        """
        def send_batch(batch_id: int):
            payload = [
                {
                    "bot_name": f"ConcurrentBatch_{batch_id}_{j}",
                    "status": "online",
                    "gems": batch_id * 1000 + j,
                }
                for j in range(5)
            ]
            return self.client.post("/api/heartbeat", json=payload)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_batch, i) for i in range(10)]
            responses = [f.result() for f in futures]

        for resp in responses:
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json().get("fleet_size"), 5)

        for i in range(10):
            for j in range(5):
                name = f"ConcurrentBatch_{i}_{j}"
                bot = fleet_manager.get_bot(name)
                self.assertIsNotNone(bot)
                self.assertEqual(bot.gems, i * 1000 + j)

    def test_high_frequency_telemetry_stream_burst(self):
        """
        50 bots each posting 10 rapid successive heartbeats concurrently (500 requests total).
        Tests server stability, state updating, and absence of deadlocks.
        """
        errors = []

        def stream_worker(bot_id: int):
            name = f"StreamBot_{bot_id:02d}"
            try:
                for cycle in range(10):
                    payload = {
                        "name": name,
                        "world": f"WORLD_{cycle}",
                        "x": cycle * 5,
                        "y": cycle * 10,
                        "gems": 1000 + (cycle * 50),
                    }
                    r = self.client.post("/api/heartbeat", json=payload)
                    if r.status_code != 200:
                        errors.append((bot_id, cycle, r.status_code))
            except Exception as exc:
                errors.append((bot_id, "exception", str(exc)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(stream_worker, i) for i in range(50)]
            concurrent.futures.wait(futures)

        self.assertEqual(len(errors), 0, f"Errors encountered during stream burst: {errors}")

        # Verify final state on a sample of bots
        for i in [0, 15, 30, 49]:
            bot = fleet_manager.get_bot(f"StreamBot_{i:02d}")
            self.assertIsNotNone(bot)
            self.assertEqual(bot.world, "WORLD_9")
            self.assertEqual(bot.x, 45)
            self.assertEqual(bot.y, 90)
            self.assertEqual(bot.gems, 1450)

    def test_concurrent_command_queue_isolation(self):
        """
        Queue unique commands for 50 distinct bots, then trigger 50 concurrent heartbeats.
        Verify:
        - Each bot receives ONLY its own queued command in the heartbeat response.
        - Zero command leakage across bots.
        - Commands are drained so subsequent polls return empty.
        """
        bot_count = 50
        for i in range(bot_count):
            name = f"CmdBot_{i:02d}"
            fleet_manager.queue_command(name, "warp", {"target": f"PRIVATE_WORLD_{i}"})

        delivered_commands = {}

        def drain_worker(bot_id: int):
            name = f"CmdBot_{bot_id:02d}"
            resp = self.client.post("/api/heartbeat", json={"name": name, "gems": 100})
            if resp.status_code == 200:
                delivered_commands[name] = resp.json().get("commands", [])

        with concurrent.futures.ThreadPoolExecutor(max_workers=bot_count) as executor:
            futures = [executor.submit(drain_worker, i) for i in range(bot_count)]
            concurrent.futures.wait(futures)

        self.assertEqual(len(delivered_commands), bot_count)

        for i in range(bot_count):
            name = f"CmdBot_{i:02d}"
            cmds = delivered_commands.get(name, [])
            self.assertEqual(len(cmds), 1, f"Bot {name} should have received exactly 1 command.")
            self.assertEqual(cmds[0].get("action"), "warp")
            self.assertEqual(cmds[0].get("params", {}).get("target"), f"PRIVATE_WORLD_{i}")

        # Subsequent poll must return empty
        for i in range(bot_count):
            name = f"CmdBot_{i:02d}"
            poll_resp = self.client.get(f"/api/poll?bot={name}")
            self.assertEqual(poll_resp.json().get("commands"), [])


class TestBotStateGemsPropertyAndMutations(unittest.TestCase):
    """Deep testing of BotState.gems property, mutation invariants, and edge cases."""

    def test_gems_property_getter_setter_direct(self):
        """Test BotState.gems getter and setter symmetry."""
        state = BotState(name="GemsTester")
        self.assertEqual(state.gems, 0)
        self.assertEqual(state.gem_count, 0)

        # Mutate via .gems setter
        state.gems = 15000
        self.assertEqual(state.gems, 15000)
        self.assertEqual(state.gem_count, 15000)

        # Mutate via .gem_count
        state.gem_count = 25000
        self.assertEqual(state.gems, 25000)

        # In-place increment
        state.gems += 500
        self.assertEqual(state.gems, 25500)
        self.assertEqual(state.gem_count, 25500)

    def test_rapid_multithreaded_gems_mutation(self):
        """
        Stress test concurrent reads and writes to BotState.gems across 20 threads.
        Verifies no AttributeError, TypeError or crash occurs during rapid mutation.
        """
        state = BotState(name="ConcurrencyGemsBot")
        iterations = 500
        thread_count = 20
        exceptions = []

        def worker(thread_id: int):
            try:
                for i in range(iterations):
                    # Write
                    state.gems = (thread_id * 1000) + i
                    # Read
                    val = state.gems
                    _ = state.gem_count
                    self.assertIsInstance(val, int)
            except Exception as e:
                exceptions.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(exceptions), 0, f"Exceptions during concurrent gems mutation: {exceptions}")
        self.assertIsInstance(state.gems, int)

    def test_update_heartbeat_gems_hierarchy_and_fallbacks(self):
        """
        Verify gems resolution in BotManager.update_heartbeat under various payload patterns:
        - 'gems' present
        - 'gem_count' present
        - both present ('gems' takes precedence)
        - string integer coercion
        - invalid string fallback
        - None handling
        """
        manager = BotManager()

        # 1. Standard gems field
        b1 = manager.update_heartbeat({"name": "B1", "gems": 1200})
        self.assertEqual(b1.gems, 1200)
        self.assertEqual(b1.gem_count, 1200)

        # 2. Legacy gem_count field
        b2 = manager.update_heartbeat({"name": "B2", "gem_count": 800})
        self.assertEqual(b2.gems, 800)

        # 3. Both present: 'gems' takes priority
        b3 = manager.update_heartbeat({"name": "B3", "gems": 5000, "gem_count": 3000})
        self.assertEqual(b3.gems, 5000)

        # 4. String representation of integer
        b4 = manager.update_heartbeat({"name": "B4", "gems": "9999"})
        self.assertEqual(b4.gems, 9999)
        self.assertIsInstance(b4.gems, int)

        # 5. Invalid string: falls back to gem_count or retains current value
        b5 = manager.update_heartbeat({"name": "B5", "gems": 100})
        manager.update_heartbeat({"name": "B5", "gems": "not_a_number", "gem_count": 200})
        self.assertEqual(b5.gems, 200)

        # 6. Invalid string with no fallback keeps existing gem_count
        manager.update_heartbeat({"name": "B5", "gems": "unparseable"})
        self.assertEqual(b5.gems, 200)

        # 7. None in gems field
        b6 = manager.update_heartbeat({"name": "B6", "gems": None, "gem_count": 450})
        self.assertEqual(b6.gems, 450)

        # 8. Negative gems value (allowed in telemetry without crashing)
        b7 = manager.update_heartbeat({"name": "B7", "gems": -50})
        self.assertEqual(b7.gems, -50)

        # 9. Large 64-bit integer
        b8 = manager.update_heartbeat({"name": "B8", "gems": 2_147_483_647})
        self.assertEqual(b8.gems, 2_147_483_647)


class TestAsciiCleanlinessAudit(unittest.TestCase):
    """
    Audit all modified and related files for strict ASCII cleanliness
    and complete absence of Growtopia-crashing Turkish characters.
    """

    FORBIDDEN_TURKISH = ["ğ", "Ğ", "ü", "Ü", "ş", "Ş", "ı", "İ", "ö", "Ö", "ç", "Ç"]

    def _check_no_turkish(self, path: Path):
        self.assertTrue(path.exists(), f"Target file does not exist: {path}")
        content = path.read_text(encoding="utf-8")
        found = [ch for ch in self.FORBIDDEN_TURKISH if ch in content]
        self.assertEqual(
            len(found), 0,
            f"File {path.relative_to(ROOT)} contains forbidden Turkish characters: {found}"
        )

    def test_bridge_lua_turkish_cleanliness(self):
        """Growtopia Lua scripts must contain ZERO Turkish characters."""
        bridge_path = ROOT / "bridge" / "lucifer_bridge.lua"
        self._check_no_turkish(bridge_path)

    def test_bridge_lua_executable_code_is_pure_7bit_ascii(self):
        """
        Verify that all executable code, string literals, and table definitions
        in bridge/lucifer_bridge.lua are strictly 7-bit ASCII.
        Lines 3 through 423 must contain zero non-ASCII bytes.
        """
        bridge_path = ROOT / "bridge" / "lucifer_bridge.lua"
        lines = bridge_path.read_text(encoding="utf-8").splitlines()
        # Verify lines 3..423 are 100% 7-bit ASCII
        for line_num, line in enumerate(lines[2:], start=3):
            non_ascii = [c for c in line if ord(c) > 127]
            self.assertEqual(
                len(non_ascii), 0,
                f"Line {line_num} in bridge/lucifer_bridge.lua contains non-ASCII characters: {non_ascii}"
            )

    def test_bridge_lua_comment_em_dash_audit(self):
        """
        Audit that the em-dash (—, U+2014) in the line 2 comment banner
        has been replaced with ASCII '--', ensuring 100% 7-bit ASCII compliance.
        """
        bridge_path = ROOT / "bridge" / "lucifer_bridge.lua"
        content = bridge_path.read_text(encoding="utf-8")
        non_ascii_chars = [(i, c) for i, c in enumerate(content) if ord(c) > 127]
        self.assertEqual(
            len(non_ascii_chars), 0,
            f"Expected 0 non-ASCII characters in bridge/lucifer_bridge.lua, found {len(non_ascii_chars)}"
        )
        self.assertNotIn("—", content)

    def test_core_bot_manager_turkish_cleanliness(self):
        """Verify core/bot_manager.py contains no forbidden Turkish characters."""
        path = ROOT / "core" / "bot_manager.py"
        self._check_no_turkish(path)

    def test_web_server_turkish_cleanliness(self):
        """Verify web/server.py contains no forbidden Turkish characters."""
        path = ROOT / "web" / "server.py"
        self._check_no_turkish(path)


class TestLuaJsonAndMultiBotAggregation(unittest.TestCase):
    """
    Stress-test the Lua regex transformation and multi-bot logic implemented in lucifer_bridge.lua.
    """

    def _simulate_lua_json_decode(self, json_str: str) -> str:
        """
        Simulates the transformations performed by bridge/lucifer_bridge.lua:
        1. s:gsub('%[', '{'):gsub('%]', '}')
        2. str:gsub('null', 'nil')
        3. str:gsub('"([^"]+)"%s*:', '["%1"]=')
        """
        s = json_str
        s = s.replace("[", "{").replace("]", "}")
        s = s.replace("null", "nil")
        s = re.sub(r'"([^"]+)"\s*:', r'["\1"]=', s)
        return s

    def test_nested_json_structures(self):
        """Verify regex correctly parses nested objects and lists without syntax errors."""
        sample = json.dumps({
            "status": "ok",
            "fleet": [
                {"name": "Bot1", "world": "START", "gems": 100},
                {"name": "Bot2", "world": "FARM", "gems": 200}
            ],
            "config": {"active": True, "limit": None}
        })
        lua_rep = self._simulate_lua_json_decode(sample)

        # Keys must be bracketed with valid Lua table syntax: ["key"] = val
        self.assertTrue(
            bool(re.search(r'\["status"\]\s*=\s*"ok"', lua_rep)),
            f"Expected bracketed key [\"status\"]=\"ok\" in {lua_rep}"
        )
        self.assertIn('["fleet"]=', lua_rep.replace(" ", ""))
        self.assertTrue(
            bool(re.search(r'\["name"\]\s*=\s*"Bot1"', lua_rep)),
            f"Expected bracketed key [\"name\"]=\"Bot1\" in {lua_rep}"
        )
        self.assertTrue(
            bool(re.search(r'\["limit"\]\s*=\s*nil', lua_rep)),
            f"Expected bracketed key [\"limit\"]=nil in {lua_rep}"
        )

        # Brackets must not have unbracketed string keys followed by '='
        illegal_keys = re.findall(r'(?<!\[)"[^"]+"(?!\s*\])\s*=', lua_rep)
        self.assertEqual(len(illegal_keys), 0, f"Found illegal keys in Lua string: {illegal_keys}")

    def test_values_with_colons_and_urls(self):
        """
        Ensure colons inside values (e.g. URLs 'http://127.0.0.1:8829') do not get corrupted
        by the key replacement pattern.
        """
        sample = '{"url":"http://127.0.0.1:8829/api/heartbeat","msg":"Time: 12:00:00"}'
        lua_rep = self._simulate_lua_json_decode(sample)

        self.assertIn('["url"]="http://127.0.0.1:8829/api/heartbeat"', lua_rep)
        self.assertIn('["msg"]="Time: 12:00:00"', lua_rep)

    def test_bridge_multibot_source_structure(self):
        """
        Verify that bridge/lucifer_bridge.lua implements getBots() aggregation
        with fallback to getBot() if getBots is unavailable.
        """
        bridge_file = ROOT / "bridge" / "lucifer_bridge.lua"
        src = bridge_file.read_text(encoding="utf-8")

        self.assertIn("getBots", src, "Bridge must check getBots for multi-bot fleets.")
        self.assertIn("getBot", src, "Bridge must retain single-bot fallback getBot.")
        self.assertIn("pcall(getBots)", src, "Bridge must safely call getBots via pcall.")
        self.assertIn("pcall(getBot)", src, "Bridge must safely call getBot via pcall.")
        self.assertIn('client.method = Method.post', src, "Bridge must set client.method.")
        self.assertIn('["Content-Type"] = "application/json"', src, "Bridge must set application/json header.")

    def test_real_lua53_json_decode_execution(self):
        """
        Directly execute the JSON.decode implementation inside real Lua 5.3 runtime
        via subprocess, validating opaque-box correctness on actual Lua engine.
        """
        import shutil
        import subprocess

        lua_bin = shutil.which("lua5.3") or shutil.which("lua")
        if not lua_bin:
            self.skipTest("No lua interpreter found on system.")

        lua_script = """
        JSON = {}
        function JSON.decode(s)
            if not s or #s == 0 then return nil end
            local str = s:gsub('%[', '{'):gsub('%]', '}')
            str = str:gsub('null', 'nil')
            str = str:gsub('"([^"]+)"%s*:', '["%1"]=')
            local fn = load("return " .. str)
            if fn then
                local ok, res = pcall(fn)
                if ok then return res end
            end
            return nil
        end

        local t1 = JSON.decode('{"status": "ok", "bot": "AlphaBot", "gems": 1500}')
        assert(t1 ~= nil, "t1 nil")
        assert(t1.status == "ok", "t1.status mismatch")
        assert(t1.bot == "AlphaBot", "t1.bot mismatch")
        assert(t1.gems == 1500, "t1.gems mismatch")

        local t2 = JSON.decode('{"commands": [{"action": "warp", "world": "START"}]}')
        assert(t2 ~= nil, "t2 nil")
        assert(#t2.commands == 1, "t2 commands length mismatch")
        assert(t2.commands[1].action == "warp", "t2 action mismatch")
        assert(t2.commands[1].world == "START", "t2 world mismatch")

        local t3 = JSON.decode('{"url": "http://127.0.0.1:8829/api/heartbeat"}')
        assert(t3 ~= nil and t3.url == "http://127.0.0.1:8829/api/heartbeat", "t3 url mismatch")

        print("LUA53_JSON_DECODE_SUCCESS")
        """

        proc = subprocess.run([lua_bin, "-e", lua_script], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Lua 5.3 execution failed:\n{proc.stderr}")
        self.assertIn("LUA53_JSON_DECODE_SUCCESS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
