"""
Milestone 2 Iteration 2 Adversarial Test Suite — Challenger 3 (m2_challenger_3)
Project: Lucifer-MCP (Prometheus AI) Modernization & Hardening

Covers:
1. /api/heartbeat with malicious payloads:
   - Malicious bot_name (lists, dicts, integers, floats, booleans, unicode, whitespace, None).
   - Batch list payloads containing non-dict items (None, ints, strings, lists, empty dicts).
   - Malformed telemetry values (Infinity, -Infinity, NaN, negative, huge strings).
2. /api/poll with malformed command entries:
   - Corrupted queue contents (list, string, int, None command entries).
   - Malformed params (list, string, int, None params).
   - Malformed code scripts (integers, None, list).
   - Hostile query parameters (?bot=, ?bot=None, path traversal, null bytes, XSS).
3. core/bot_manager.py telemetry stress & type coercion:
   - gem_count and gems resolution (strings, negative, None, floats, objects, inf, -inf, nan).
   - Safe conversion for raw_status, google_status, x, y, pearl_count, voucher_count, level, ping.
   - captcha_status string telemetry ('solving', 'wrong', 'failed') vs integer conversion.
   - get_fleet_summary resilience.
4. bridge/lucifer_bridge.lua JSON decoding & ASCII cleanliness:
   - Deep nested structures, escaped quotes, bracket preservation for automation scripts.
   - Zero non-ASCII byte audit.
"""
from __future__ import annotations

import math
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient
from web.server import app
from core.bot_manager import BotManager, BotState, fleet_manager

LUA_BRIDGE_PATH = ROOT / "bridge" / "lucifer_bridge.lua"


def _extract_lua_json_block() -> str:
    """Extracts the exact JSON module implementation directly from bridge/lucifer_bridge.lua."""
    content = LUA_BRIDGE_PATH.read_text(encoding="utf-8")
    start_marker = "local JSON = {}"
    end_marker = "-- ========================================================================="
    idx_start = content.index(start_marker)
    idx_end = content.index(end_marker, idx_start)
    return content[idx_start:idx_end]


class TestHeartbeatAdversarialPayloads(unittest.TestCase):
    """Rigorous tests for POST /api/heartbeat against hostile and malformed payloads."""

    def setUp(self):
        # Disable raise_server_exceptions to observe real HTTP status codes (400 vs 500)
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_heartbeat_bot_name_type_coercion_zero_crashes(self):
        """
        Verify /api/heartbeat safely handles non-string, unhashable, or exotic bot_name types
        without raising 500 Internal Server Error.
        """
        hostile_bot_names: list[tuple[Any, str]] = [
            (None, "None type"),
            ([], "empty list"),
            (["Alpha", "Beta"], "nested list"),
            ({}, "empty dict"),
            ({"cluster": "asia", "id": 99}, "nested dict"),
            (0, "integer zero"),
            (12345, "positive integer"),
            (-999, "negative integer"),
            (3.14159, "float number"),
            (True, "boolean True"),
            (False, "boolean False"),
            ("   \t\r\n  ", "whitespace only"),
            ("🤖_Lucifer_\u2620", "unicode emoji and symbols"),
            ("N\u00fcr\u00f6nB\u00f6t", "unicode umlauts"),
            ("\x00\x01\x02", "null and control characters"),
            ("A" * 5000, "very long string"),
        ]

        for bot_name_val, desc in hostile_bot_names:
            payload = {"bot_name": bot_name_val, "status": "online", "gems": 100}
            resp = self.client.post("/api/heartbeat", json=payload)
            self.assertEqual(
                resp.status_code, 200,
                f"Heartbeat failed for bot_name [{desc}]: status {resp.status_code}, response: {resp.text}"
            )
            data = resp.json()
            self.assertEqual(data.get("status"), "ok")
            self.assertIsInstance(data.get("bot"), str)
            self.assertGreater(len(data.get("bot")), 0)

    def test_heartbeat_batch_list_with_corrupted_items(self):
        """
        Verify /api/heartbeat batch array payloads containing non-dict, null, and primitive items
        filter them gracefully and update valid items without 500 crashes.
        """
        malicious_batch = [
            None,
            12345,
            "just_a_string",
            [1, 2, 3],
            {},  # empty dict -> defaults to unknown
            {"bot_name": "ValidBot_1", "gems": 500},
            {"bot_name": ["nested", "name"], "gems": "bad_gems"},
            {"bot_name": "ValidBot_2", "gems": 1000},
            False,
        ]

        resp = self.client.post("/api/heartbeat", json=malicious_batch)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("fleet_size"), len(malicious_batch))
        commands = data.get("commands", {})
        self.assertIn("ValidBot_1", commands)
        self.assertIn("ValidBot_2", commands)

    def test_heartbeat_root_primitives_return_400_not_500(self):
        """Verify non-object/non-list root JSON values return 400 Bad Request, never 500."""
        primitives = [
            b"12345",
            b'"bare string"',
            b"true",
            b"false",
            b"null",
        ]
        for prim in primitives:
            resp = self.client.post(
                "/api/heartbeat",
                content=prim,
                headers={"Content-Type": "application/json"}
            )
            self.assertEqual(
                resp.status_code, 400,
                f"Expected 400 for primitive payload {prim!r}, got {resp.status_code}: {resp.text}"
            )

    def test_heartbeat_float_infinity_and_nan_handling(self):
        """
        Adversarial Test:
        JSON specification supports Infinity / -Infinity / NaN in Python json.loads.
        Verify that passing Infinity or -Infinity in gems or telemetry does NOT cause
        an unhandled OverflowError / 500 Internal Server Error.
        """
        # Testing JSON with Infinity
        raw_payload = b'{"bot_name": "InfBot", "gems": Infinity, "level": 10}'
        resp = self.client.post(
            "/api/heartbeat",
            content=raw_payload,
            headers={"Content-Type": "application/json"}
        )
        self.assertNotEqual(
            resp.status_code, 500,
            f"Heartbeat crashed with 500 Internal Server Error on Infinity gems: {resp.text}"
        )
        self.assertEqual(resp.status_code, 200)


class TestPollMalformedCommandsAdversarial(unittest.TestCase):
    """Rigorous tests for GET /api/poll handling hostile queue states and parameters."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_poll_with_corrupted_command_entries(self):
        """
        Adversarial challenge:
        Queue contains corrupted non-dict entries:
        - List entry: ['warp', 'WORLD']
        - String entry: 'warp WORLD'
        - Integer entry: 999
        - None entry: None
        Verify /api/poll drains the queue cleanly and returns 200 without AttributeError.
        """
        test_bot = "CorruptQueueBot"
        fleet_manager._command_queues[test_bot] = [
            ["warp", "START"],
            "raw_string_command",
            12345,
            None,
            {"action": "warp", "params": {"world": "SAFE_WORLD"}},
        ]

        resp = self.client.get(f"/api/poll?bot={test_bot}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("bot"), test_bot)
        # Commands must be delivered
        self.assertEqual(len(data.get("commands")), 5)
        # Since first command was a list, top-level 'command' should safely default to empty string
        self.assertEqual(data.get("command"), "")
        self.assertEqual(data.get("script"), "")

        # Queue must now be drained
        resp2 = self.client.get(f"/api/poll?bot={test_bot}")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json().get("commands"), [])

    def test_poll_with_malformed_command_params(self):
        """
        Adversarial challenge:
        First command is a dict, but 'params' is not a dict:
        - params = [1, 2, 3] (list)
        - params = 'code_only' (string)
        - params = 42 (integer)
        - params = None
        - params = {'code': 99999} (non-string code)
        - params = {'code': None}
        Verify /api/poll extracts 'command' action and safely defaults 'script'.
        """
        cases = [
            ({"action": "warp", "params": ["START", 10, 20]}, "warp", ""),
            ({"action": "drop", "params": "item_242"}, "drop", ""),
            ({"action": "sleep", "params": 5000}, "sleep", ""),
            ({"action": "jump", "params": None}, "jump", ""),
            ({"action": "run_script", "params": {"code": 12345}}, "run_script", 12345),
            ({"action": "run_script", "params": {"code": None}}, "run_script", ""),
        ]

        for idx, (cmd_entry, expected_action, expected_code) in enumerate(cases):
            bot_name = f"ParamTestBot_{idx}"
            fleet_manager._command_queues[bot_name] = [cmd_entry]
            resp = self.client.get(f"/api/poll?bot={bot_name}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get("command"), expected_action)
            if expected_code == "":
                self.assertIn(data.get("script"), ("", None))
            else:
                self.assertEqual(data.get("script"), expected_code)

    def test_poll_hostile_query_parameters(self):
        """
        Verify /api/poll query parameter sanitization against malicious path traversals,
        injection attacks, and empty values.
        """
        hostile_bots = [
            ("", "global"),
            ("   ", "global"),
            ("None", "None"),
            ("../../../etc/passwd", "../../../etc/passwd"),
            ("<script>alert(1)</script>", "<script>alert(1)</script>"),
            ("%00nullbyte", "\x00nullbyte"),
            ("🤖_Bot_🔥", "🤖_Bot_🔥"),
        ]

        for query_val, expected_sanitized in hostile_bots:
            resp = self.client.get(f"/api/poll?bot={query_val}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("bot"), expected_sanitized)


class TestBotManagerTelemetryStress(unittest.TestCase):
    """Stress testing BotManager and BotState against hostile and edge-case inputs."""

    def setUp(self):
        self.manager = BotManager()

    def test_gems_resolution_hierarchy_and_fallbacks(self):
        """
        Verify gem_count/gems hierarchy:
        1. 'gems' takes precedence if valid integer or coercible.
        2. If 'gems' is invalid/unparseable, fallback to 'gem_count'.
        3. If both invalid, fallback to previous gem_count or 0.
        """
        bot = self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": 500})
        self.assertEqual(bot.gem_count, 500)
        self.assertEqual(bot.gems, 500)

        # 'gems' coercible from string
        self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": "1200"})
        self.assertEqual(bot.gem_count, 1200)

        # 'gems' is negative integer
        self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": -250})
        self.assertEqual(bot.gem_count, -250)

        # 'gems' is float (coerced via int)
        self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": 399.9})
        self.assertEqual(bot.gem_count, 399)

        # 'gems' is invalid string, 'gem_count' is valid integer
        self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": "not_a_number", "gem_count": 850})
        self.assertEqual(bot.gem_count, 850)

        # 'gems' is an unhashable dict, 'gem_count' is valid
        self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": {"fake": 1}, "gem_count": 700})
        self.assertEqual(bot.gem_count, 700)

        # Both 'gems' and 'gem_count' are invalid objects -> preserves existing valid value
        self.manager.update_heartbeat({"bot_name": "GemsBot", "gems": [1, 2], "gem_count": "invalid"})
        self.assertEqual(bot.gem_count, 700)

    def test_telemetry_numeric_fields_type_safety(self):
        """
        Verify numeric telemetry fields safely convert valid numbers and ignore malformed
        types without crashing:
        Fields: raw_status, google_status, x, y, pearl_count, voucher_count, level, ping.
        """
        fields = [
            "raw_status",
            "google_status",
            "x",
            "y",
            "pearl_count",
            "voucher_count",
            "level",
            "ping",
        ]

        # Valid numeric string inputs
        valid_payload = {f: "42" for f in fields}
        valid_payload["bot_name"] = "NumericTester"
        bot = self.manager.update_heartbeat(valid_payload)
        for f in fields:
            self.assertEqual(getattr(bot, f), 42, f"Field {f} failed string int conversion")

        # Malformed non-numeric types must not raise exceptions and preserve defaults or prior
        bad_payload = {f: [1, 2, 3] for f in fields}
        bad_payload["bot_name"] = "NumericTester"
        bot = self.manager.update_heartbeat(bad_payload)
        for f in fields:
            self.assertEqual(getattr(bot, f), 42, f"Field {f} was corrupted by bad type")

    def test_float_infinity_and_nan_in_update_heartbeat_zero_crashes(self):
        """
        Adversarial Defect Target:
        int(float('inf')) raises OverflowError in Python.
        Verify that update_heartbeat catches OverflowError gracefully across all numeric fields.
        """
        fields = ["gems", "gem_count", "raw_status", "google_status", "x", "y", "level", "ping"]
        for f in fields:
            for bad_val in (float("inf"), float("-inf"), float("nan")):
                try:
                    bot = self.manager.update_heartbeat({"bot_name": f"Inf_{f}", f: bad_val})
                    # Must be a valid integer
                    self.assertIsInstance(getattr(bot, f if f != "gems" else "gem_count"), int)
                except OverflowError as exc:
                    self.fail(f"Field '{f}' raised unhandled OverflowError with value {bad_val}: {exc}")

    def test_captcha_status_string_telemetry_contract(self):
        """
        Contract Verification:
        bridge/lucifer_bridge.lua sends captcha_status as a string ('solving', 'wrong', 'failed').
        BotState.has_captcha checks: self.captcha_status in ('solving', 'wrong', 'captcha_requested', 'failed').
        Verify update_heartbeat correctly updates bot.captcha_status to string and triggers has_captcha.
        """
        alerts = []
        self.manager.subscribe_event(lambda evt, data: alerts.append((evt, data)))

        bot = self.manager.update_heartbeat({"bot_name": "CaptchaBot", "captcha_status": "solving"})
        self.assertEqual(
            bot.captcha_status, "solving",
            f"bot.captcha_status should be string 'solving', got: {bot.captcha_status!r}"
        )
        self.assertTrue(
            bot.has_captcha,
            f"bot.has_captcha should be True when captcha_status is 'solving', got: {bot.has_captcha}"
        )

        # Check captcha alert dispatch
        captcha_events = [data for evt, data in alerts if evt == "captcha_alert"]
        self.assertGreater(
            len(captcha_events), 0,
            "Expected 'captcha_alert' event to be dispatched when captcha_status transitioned to 'solving'."
        )

    def test_fleet_summary_resilience_to_hostile_bots(self):
        """Verify get_fleet_summary handles bots with negative gems, large fleets, and offline bots."""
        bm = BotManager()
        bm.update_heartbeat({"bot_name": "b1", "gems": 1000})
        bm.update_heartbeat({"bot_name": "b2", "gems": -200})
        bm.update_heartbeat({"bot_name": "b3", "gems": 0})
        bm.update_heartbeat({"bot_name": "b4", "status": "captcha_requested"})

        summary = bm.get_fleet_summary()
        self.assertEqual(summary["total_bots"], 4)
        self.assertEqual(summary["total_gems"], 800)
        self.assertGreaterEqual(summary["captcha_alerts"], 1)


class TestLuaBridgeAdversarialJSONAndASCII(unittest.TestCase):
    """Rigorous tests for bridge/lucifer_bridge.lua JSON decoding and ASCII cleanliness."""

    def setUp(self):
        self.assertTrue(LUA_BRIDGE_PATH.exists())
        self.json_block = _extract_lua_json_block()

    def _run_lua_snippet(self, lua_code: str) -> str:
        import shutil
        if shutil.which("lua"):
            proc = subprocess.run(["lua", "-e", lua_code], capture_output=True, text=True, timeout=5)
            return proc.stdout.strip()
        from lupa import LuaRuntime
        lua = LuaRuntime()
        captured = []
        lua.globals()["print"] = lambda *args: captured.append(" ".join(str(a) for a in args))
        lua.execute("if os then os.exit = function(c) error('LUA_EXIT_' .. tostring(c or 0)) end end")
        lua.execute(lua_code)
        return "\n".join(captured).strip()

    def _execute_lua_decode(self, payload_str: str) -> tuple[bool, Any]:
        """Runs JSON.decode inside real Lua runtime."""
        lua_code = f"""
        {self.json_block}
        local res = JSON.decode([==[{payload_str}]==])
        if res ~= nil then
            print("OK")
        else
            print("NIL")
        end
        """
        out = self._run_lua_snippet(lua_code)
        return (out == "OK", out)

    def test_deep_nested_and_heterogeneous_structures(self):
        """Test nested arrays, objects, booleans, and nulls decode cleanly."""
        sample = '{"a": {"b": [{"c": true, "d": false, "e": null, "f": 123.45}]}}'
        ok, msg = self._execute_lua_decode(sample)
        self.assertTrue(ok, f"Failed decoding complex nested structure: {msg}")

    def test_escaped_quotes_and_control_chars(self):
        """Test escaped quotes, newlines, tabs, and backslashes inside JSON strings."""
        sample = '{"text": "Line1\\nLine2\\tTabbed \\"Quoted\\" and \\\\Backslash\\/Slash"}'
        ok, msg = self._execute_lua_decode(sample)
        self.assertTrue(ok, f"Failed decoding escaped quotes/control chars: {msg}")

    def test_bracket_preservation_for_lua_scripts(self):
        """Verify automation script square brackets (e.g. inv[1] = 5) are preserved."""
        script_code = 'local inv = bot:getInventory()\\ninv[1] = 5 and item[2] == 10'
        payload = f'{{"action": "run_script", "params": {{"code": "{script_code}"}}}}'
        lua_code = f"""
        {self.json_block}
        local res = JSON.decode([==[{payload}]==])
        if not res or not res.params or not res.params.code then
            print("NIL_RES")
            os.exit(1)
        end
        local chunk, err = load(res.params.code)
        if not chunk then
            print("SYNTAX_ERROR: " .. tostring(err))
        else
            print("VALID_CHUNK")
        end
        """
        out = self._run_lua_snippet(lua_code)
        self.assertEqual(out, "VALID_CHUNK", f"Lua bracket preservation failed: {out}")

    def test_strict_zero_non_ascii_bytes_in_bridge_lua(self):
        """
        Strict 7-bit ASCII compliance audit for Growtopia font engine compatibility.
        bridge/lucifer_bridge.lua must contain 0 non-ASCII bytes.
        """
        raw_bytes = LUA_BRIDGE_PATH.read_bytes()
        non_ascii = [(idx + 1, b, hex(b)) for idx, b in enumerate(raw_bytes) if b > 127]
        self.assertEqual(
            len(non_ascii), 0,
            f"bridge/lucifer_bridge.lua contains non-ASCII bytes: {non_ascii}"
        )


if __name__ == "__main__":
    unittest.main()
