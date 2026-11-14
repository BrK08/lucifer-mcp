"""
Milestone 2 Adversarial Stress Test Suite — Challenger 1 (m2_challenger_1)
Project: Lucifer-MCP (Prometheus AI) Modernization & Hardening

Empirical Challenges for Milestone 2:
1. /api/heartbeat Stress:
   - Malformed JSON (syntax errors, non-JSON streams) -> Expects 400/422, zero 500s.
   - Empty payloads ({}, [], None) -> Expects safe defaults, zero 500s.
   - Missing bot names (missing keys, empty strings, nulls) -> Defaults safely.
   - Unhashable bot_name (list/dict) -> Detects HTTP 500 bug.
   - Unexpected telemetry types (corrupted gem_count list) -> Detects 500 crash on /api/fleet/summary.
   - Concurrent heartbeat bursts (100 concurrent workers) -> Stress tests concurrency.
2. /api/poll Stress:
   - Missing bot query parameter (?bot omitted) -> Defaults to 'global'.
   - Empty string (?bot=) -> Defaults to 'global'.
   - Special characters (?bot=%00, ?bot=../../../etc/passwd, ?bot=<script>alert(1)</script>) -> Zero crashes.
   - Non-dict command params in queue -> Detects HTTP 500 AttributeError bug.
3. Lua JSON.decode Pattern Stress (tested in real Lua 5.3 runtime using bridge/lucifer_bridge.lua):
   - Normal colons inside string values ("http://...") -> Passes.
   - Deep nested objects and arrays -> Passes.
   - Escaped quotes with colons ('{"msg": "User \\"Alice\\": joined"}') -> Detects regex failure (returns nil).
   - Embedded serialized JSON string ('{"config": "{\\"key\\": 1}"}') -> Detects regex failure (returns nil).
   - Bracket replacement side-effects on Lua automation code ('inv[1] = 5') -> Detects Lua code syntax error.
4. Lua 7-bit ASCII Compliance:
   - Audit all bytes in bridge/lucifer_bridge.lua -> Detects 3 non-ASCII bytes (UTF-8 em-dash 226, 128, 148).
"""
from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import unittest
from pathlib import Path

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


class TestHeartbeatAdversarialStress(unittest.TestCase):
    """Stress tests for POST /api/heartbeat handling hostile and malformed inputs."""

    def setUp(self):
        # Disable raise_server_exceptions so TestClient acts like a real HTTP client
        # and returns 500 when an unhandled server exception occurs.
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_malformed_json_body_returns_400_not_500(self):
        """Verify malformed JSON strings return 400 Bad Request, never 500."""
        malformed_bodies = [
            b"{not_json: true",
            b"{{{{",
            b"",
            b"null",
            b"12345",
            b'"just a string"',
            b"[1, 2, 3",
        ]
        for body in malformed_bodies:
            resp = self.client.post(
                "/api/heartbeat",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            self.assertIn(
                resp.status_code,
                (400, 422),
                f"Body {body!r} returned unexpected status {resp.status_code}: {resp.text}",
            )
            self.assertNotEqual(resp.status_code, 500, f"Body {body!r} caused 500 Internal Server Error!")

    def test_empty_dict_and_empty_list_payloads(self):
        """Verify empty dict and empty list return 200 without crashing."""
        resp_dict = self.client.post("/api/heartbeat", json={})
        self.assertEqual(resp_dict.status_code, 200)
        self.assertEqual(resp_dict.json().get("status"), "ok")

        resp_list = self.client.post("/api/heartbeat", json=[])
        self.assertEqual(resp_list.status_code, 200)
        self.assertEqual(resp_list.json().get("status"), "ok")
        self.assertEqual(resp_list.json().get("fleet_size"), 0)

    def test_missing_or_empty_bot_names(self):
        """Verify payload with missing, empty, or whitespace bot names defaults safely."""
        test_payloads = [
            {"world": "START", "status": 1},
            {"name": "", "status": 1},
            {"bot_name": "", "status": 1},
            {"bot": None, "status": 1},
            {"name": "   ", "status": 1},
        ]
        for payload in test_payloads:
            resp = self.client.post("/api/heartbeat", json=payload)
            self.assertEqual(
                resp.status_code, 200,
                f"Payload {payload} failed with status {resp.status_code}: {resp.text}"
            )
            data = resp.json()
            self.assertEqual(data.get("status"), "ok")
            self.assertTrue(len(data.get("bot", "")) > 0)

    def test_unhashable_bot_name_causes_500_defect(self):
        """
        Hardening Verification:
        Sending an unhashable type (list or dict) as bot name is sanitized safely,
        preventing TypeError and HTTP 500.
        """
        resp = self.client.post("/api/heartbeat", json={"name": ["bot_in_a_list"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("bot", data)

    def test_unexpected_data_types_in_telemetry_fields_causes_500_defect(self):
        """
        Hardening Verification:
        Sending a list as gem_count is coerced safely without corrupting BotState.gem_count.
        Subsequent calls to /api/fleet/summary succeed with HTTP 200 without TypeError.
        """
        corrupt_payload = {
            "name": "CorruptBot_01",
            "gem_count": [100, 200],  # list instead of int
        }
        resp = self.client.post("/api/heartbeat", json=corrupt_payload)
        self.assertEqual(resp.status_code, 200)

        # /api/fleet/summary succeeds with 200:
        summary_resp = self.client.get("/api/fleet/summary")
        self.assertEqual(
            summary_resp.status_code, 200,
            f"Expected 200: /api/fleet/summary failed with {summary_resp.status_code}: {summary_resp.text}"
        )
        self.assertIsInstance(summary_resp.json().get("total_gems"), int)

    def test_concurrent_heartbeat_bursts(self):
        """
        Concurrency Stress: 100 concurrent heartbeats fired simultaneously across 20 threads.
        Verifies thread-safety and zero transport drops under nominal payloads.
        """
        burst_size = 100
        errors = []

        def send_hb(idx: int):
            payload = {
                "bot_name": f"BurstBot_{idx:03d}",
                "status": "online",
                "world": f"WORLD_{idx % 10}",
                "gems": idx * 50,
            }
            try:
                r = self.client.post("/api/heartbeat", json=payload)
                if r.status_code != 200:
                    errors.append((idx, r.status_code, r.text))
            except Exception as e:
                errors.append((idx, 500, str(e)))

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(send_hb, i) for i in range(burst_size)]
            concurrent.futures.wait(futures)

        self.assertEqual(len(errors), 0, f"Concurrent heartbeat errors occurred: {errors}")


class TestPollAdversarialStress(unittest.TestCase):
    """Stress tests for GET /api/poll handling hostile queries and corrupted queues."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_poll_missing_bot_query_defaults_to_global(self):
        """Verify GET /api/poll without query param defaults to 'global' safely."""
        resp = self.client.get("/api/poll")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("bot"), "global")

    def test_poll_empty_string_bot_query(self):
        """Verify GET /api/poll?bot= handles empty string safely."""
        resp = self.client.get("/api/poll?bot=")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("bot"), "global")

    def test_poll_special_characters_and_injections(self):
        """Verify GET /api/poll with malicious/special characters does not crash."""
        special_names = [
            "../../../etc/passwd",
            "<script>alert(1)</script>",
            "bot with spaces",
            "bot' OR '1'='1",
            "%00nullbyte",
            "🤖_emoji_bot",
        ]
        for name in special_names:
            resp = self.client.get(f"/api/poll?bot={name}")
            self.assertEqual(
                resp.status_code, 200,
                f"Poll with bot query {name!r} returned {resp.status_code}: {resp.text}"
            )
            data = resp.json()
            self.assertEqual(data.get("status"), "ok")

    def test_poll_with_non_dict_params_in_queue_causes_500_defect(self):
        """
        Hardening Verification:
        When a queued command contains non-dict params (string or list):
        GET /api/poll handles it safely and returns HTTP 200 with fallback empty params.
        """
        bot_target = "CorruptQueueBot"
        fleet_manager.queue_command(bot_target, "test_action", "string_params_instead_of_dict")
        resp = self.client.get(f"/api/poll?bot={bot_target}")
        self.assertEqual(
            resp.status_code, 200,
            f"Expected 200: /api/poll failed with {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("script"), "")


class TestLuaBridgeRegexAdversarialStress(unittest.TestCase):
    """Stress tests for bridge/lucifer_bridge.lua JSON.decode regex and deserialization."""

    @classmethod
    def setUpClass(cls):
        cls.json_block = _extract_lua_json_block()

    def _run_lua_snippet(self, lua_code: str) -> str:
        import shutil
        if shutil.which("lua"):
            proc = subprocess.run(
                ["lua", "-e", lua_code],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return proc.stdout.strip()
        from lupa import LuaRuntime
        lua = LuaRuntime()
        captured = []
        lua.globals()["print"] = lambda *args: captured.append(" ".join(str(a) for a in args))
        lua.execute("if os then os.exit = function(c) error('LUA_EXIT_' .. tostring(c or 0)) end end")
        lua.execute(lua_code)
        return "\n".join(captured).strip()

    def _execute_lua_decode(self, payload_str: str) -> tuple[bool, str]:
        lua_code = f"""
        {self.json_block}
        local res = JSON.decode([==[{payload_str}]==])
        if res then
            print("SUCCESS")
        else
            print("FAILED")
        end
        """
        out = self._run_lua_snippet(lua_code)
        return (out == "SUCCESS", out)

    def test_colons_inside_normal_string_values_succeeds(self):
        """Verify URL string values with colons deserialize successfully."""
        sample = '{"url": "http://127.0.0.1:8829/api/heartbeat", "time": "12:30:45"}'
        ok, msg = self._execute_lua_decode(sample)
        self.assertTrue(ok, f"Failed to decode URLs with colons: {msg}")

    def test_nested_objects_and_arrays_succeeds(self):
        """Verify deeply nested dictionaries and arrays decode properly."""
        sample = '{"commands": [{"action": "warp", "params": {"world": "START", "x": 10, "y": 20}}]}'
        ok, msg = self._execute_lua_decode(sample)
        self.assertTrue(ok, f"Failed to decode nested structures: {msg}")

    def test_escaped_quotes_before_colons_fails_defect(self):
        """
        Hardening Verification:
        Escaped quotes before colons inside string values: '{"msg": "User \\"Alice\\": joined"}'
        JSON.decode successfully deserializes without error.
        """
        sample = '{"msg": "User \\"Alice\\": joined"}'
        ok, msg = self._execute_lua_decode(sample)
        self.assertTrue(
            ok,
            f"Expected JSON.decode to succeed with escaped quotes: {msg}"
        )

    def test_embedded_serialized_json_string_fails_defect(self):
        """
        Hardening Verification:
        JSON string containing another stringified JSON object:
        '{"action": "set_config", "params": {"config": "{\\"target\\": 5666}"}}'
        JSON.decode successfully deserializes embedded JSON string.
        """
        sample = '{"action": "set_config", "params": {"config": "{\\"target\\": 5666}"}}'
        ok, msg = self._execute_lua_decode(sample)
        self.assertTrue(
            ok,
            f"Expected JSON.decode to succeed with embedded JSON string: {msg}"
        )

    def test_lua_code_array_indexing_brackets_corrupted_defect(self):
        """
        Hardening Verification:
        Automation script containing Lua array indexing:
        'local inv = bot:getInventory()\\ninv[1] = 5'
        JSON.decode preserves square brackets inside string literals, allowing load() to succeed.
        """
        payload = '{"action": "run_script", "params": {"code": "local inv = bot:getInventory()\\ninv[1] = 5"}}'
        lua_code = f"""
        {self.json_block}
        local res = JSON.decode([==[{payload}]==])
        if not res or not res.params or not res.params.code then
            print("DECODE_NIL")
            os.exit(1)
        end
        local chunk, err = load(res.params.code)
        if not chunk then
            print("SYNTAX_ERROR: " .. tostring(err))
        else
            print("SYNTAX_OK")
        end
        """
        out = self._run_lua_snippet(lua_code)
        self.assertEqual(
            out, "SYNTAX_OK",
            f"Expected SYNTAX_OK for preserved Lua script array indexing, got: {out}"
        )


class TestBridgeLuaAsciiIntegrity(unittest.TestCase):
    """Audit strict 7-bit ASCII cleanliness of bridge/lucifer_bridge.lua."""

    def test_bridge_lua_non_ascii_bytes_defect(self):
        """
        Hardening Verification:
        Growtopia font engine requires 100% 7-bit ASCII.
        Audits that bridge/lucifer_bridge.lua has 0 non-ASCII bytes.
        """
        self.assertTrue(LUA_BRIDGE_PATH.exists())
        raw_bytes = LUA_BRIDGE_PATH.read_bytes()
        non_ascii = [(idx + 1, b) for idx, b in enumerate(raw_bytes) if b > 127]
        self.assertEqual(
            len(non_ascii), 0,
            f"bridge/lucifer_bridge.lua must contain 0 non-ASCII bytes, found: {non_ascii}"
        )


if __name__ == "__main__":
    unittest.main()
