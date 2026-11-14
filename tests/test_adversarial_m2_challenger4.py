"""
Milestone 2 Iteration 3 Adversarial Test Suite — Challenger 4 (m2_challenger_4)
Project: Lucifer-MCP (Prometheus AI) Modernization & Hardening

Challenger Mission:
1. Re-verify Milestone 2 Iteration 2/3 test suites.
2. Adversarial stress against /api/heartbeat with:
   - Infinity, -Infinity, NaN (unquoted JSON numeric constants)
   - "solving" for captcha_status
   - Quoted strings "Infinity", "-Infinity", "NaN"
   - Batch payloads with mixed adversarial constants
   - Concurrency stress under hostile telemetry
   - Event subscriber alert dispatching and deduplication
   - Downstream endpoint resilience (/api/fleet/summary, /api/bot/{name}, /api/poll)
"""
from __future__ import annotations

import concurrent.futures
import math
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
from core.enums import BotStatus


class TestHeartbeatCaptchaAndFloatExtremes(unittest.TestCase):
    """Adversarial challenge for /api/heartbeat with Infinity, -Infinity, NaN, and 'solving'."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        self.local_manager = BotManager()

    def test_heartbeat_captcha_status_unquoted_infinity_ninf_nan(self):
        """
        Challenge /api/heartbeat with unquoted JSON numeric constants:
        - captcha_status: Infinity
        - captcha_status: -Infinity
        - captcha_status: NaN
        Verifies HTTP 200, string coercion to 'inf'/'-inf'/'nan', and bot.has_captcha is False.
        """
        test_cases = [
            (b'{"bot_name": "InfCaptchaBot", "captcha_status": Infinity}', "InfCaptchaBot", "inf"),
            (b'{"bot_name": "NInfCaptchaBot", "captcha_status": -Infinity}', "NInfCaptchaBot", "-inf"),
            (b'{"bot_name": "NaNCaptchaBot", "captcha_status": NaN}', "NaNCaptchaBot", "nan"),
        ]

        for raw_payload, expected_name, expected_str in test_cases:
            resp = self.client.post(
                "/api/heartbeat",
                content=raw_payload,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(
                resp.status_code, 200,
                f"Heartbeat failed for payload {raw_payload.decode()}: {resp.status_code} {resp.text}"
            )
            data = resp.json()
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("bot"), expected_name)

            bot = fleet_manager.get_bot(expected_name)
            self.assertIsNotNone(bot)
            self.assertEqual(bot.captcha_status, expected_str)
            self.assertIsInstance(bot.captcha_status, str)
            self.assertFalse(bot.has_captcha)

    def test_heartbeat_captcha_status_solving(self):
        """
        Challenge /api/heartbeat with captcha_status: "solving".
        Verifies:
        - HTTP 200 returned.
        - bot.captcha_status set to "solving".
        - bot.has_captcha evaluates to True.
        - captcha_alert event is dispatched to subscribers.
        - fleet summary reflects active captcha alerts.
        """
        captured_events: list[tuple[str, dict[str, Any]]] = []

        def event_handler(evt: str, data: dict[str, Any]):
            captured_events.append((evt, data))

        fleet_manager.subscribe_event(event_handler)

        bot_name = "SolvingCaptchaBot"
        payload = {
            "bot_name": bot_name,
            "status": "online",
            "captcha_status": "solving",
            "captcha_url": "https://growtopia2.com/player/growid/check_captcha?token=abc123xyz",
        }

        resp = self.client.post("/api/heartbeat", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("bot"), bot_name)

        bot = fleet_manager.get_bot(bot_name)
        self.assertIsNotNone(bot)
        self.assertEqual(bot.captcha_status, "solving")
        self.assertTrue(bot.has_captcha)

        # Check dispatched event
        matching_alerts = [
            d for e, d in captured_events if e == "captcha_alert" and d.get("bot") == bot_name
        ]
        self.assertEqual(len(matching_alerts), 1)
        self.assertEqual(matching_alerts[0].get("captcha_status"), "solving")
        self.assertIn("growid/check_captcha", matching_alerts[0].get("captcha_url", ""))

        # Fleet summary verification
        summary = fleet_manager.get_fleet_summary()
        self.assertGreaterEqual(summary["captcha_alerts"], 1)

    def test_heartbeat_captcha_status_quoted_string_variants(self):
        """
        Challenge /api/heartbeat with string variations of Infinity, -Infinity, NaN,
        as well as standard captcha statuses ('wrong', 'failed', 'captcha_requested', 'no_captcha').
        """
        cases = [
            ("Infinity", False),
            ("-Infinity", False),
            ("NaN", False),
            ("solving", True),
            ("wrong", True),
            ("failed", True),
            ("captcha_requested", True),
            ("no_captcha", False),
            ("solved", False),
            ("unknown_status", False),
        ]

        for status_val, expected_has_captcha in cases:
            bname = f"QuotedBot_{status_val.replace('-', 'neg_')}"
            resp = self.client.post("/api/heartbeat", json={"bot_name": bname, "captcha_status": status_val})
            self.assertEqual(resp.status_code, 200)
            bot = fleet_manager.get_bot(bname)
            self.assertIsNotNone(bot)
            self.assertEqual(bot.captcha_status, status_val)
            self.assertEqual(
                bot.has_captcha, expected_has_captcha,
                f"bot.has_captcha for status '{status_val}' expected {expected_has_captcha}, got {bot.has_captcha}"
            )

    def test_heartbeat_all_telemetry_fields_with_infinity_and_nan(self):
        """
        Stress challenge where every numeric field in the heartbeat payload contains
        unquoted Infinity, -Infinity, or NaN alongside captcha_status='solving'.
        Must not raise OverflowError or crash with HTTP 500.
        """
        payload_bytes = b"""{
            "bot_name": "FullExtremeChaosBot",
            "captcha_status": "solving",
            "gems": Infinity,
            "gem_count": -Infinity,
            "raw_status": NaN,
            "google_status": Infinity,
            "x": -Infinity,
            "y": NaN,
            "pearl_count": Infinity,
            "voucher_count": -Infinity,
            "level": NaN,
            "ping": Infinity
        }"""

        resp = self.client.post(
            "/api/heartbeat",
            content=payload_bytes,
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp.status_code, 200, f"Full chaos heartbeat crashed: {resp.text}")
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("bot"), "FullExtremeChaosBot")

        bot = fleet_manager.get_bot("FullExtremeChaosBot")
        self.assertIsNotNone(bot)
        self.assertEqual(bot.captcha_status, "solving")
        self.assertTrue(bot.has_captcha)
        self.assertIsInstance(bot.gem_count, int)
        self.assertIsInstance(bot.x, int)
        self.assertIsInstance(bot.y, int)
        self.assertIsInstance(bot.raw_status, int)
        self.assertIsInstance(bot.google_status, int)
        self.assertIsInstance(bot.pearl_count, int)
        self.assertIsInstance(bot.voucher_count, int)
        self.assertIsInstance(bot.level, int)
        self.assertIsInstance(bot.ping, int)

    def test_downstream_endpoints_resilience_after_extreme_heartbeats(self):
        """
        Ensure that downstream REST endpoints:
        - GET /api/fleet/summary
        - GET /fleet/summary
        - GET /api/bot/{name}
        - GET /api/poll?bot={name}
        encode valid RFC-compliant JSON without crashing (allow_nan=False compliance).
        """
        # Seed bot with extreme values
        seed_payload = b"""{
            "bot_name": "DownstreamSafeBot",
            "captcha_status": "solving",
            "gems": Infinity,
            "x": NaN,
            "y": -Infinity
        }"""
        r_post = self.client.post("/api/heartbeat", content=seed_payload, headers={"Content-Type": "application/json"})
        self.assertEqual(r_post.status_code, 200)

        # Query GET /api/fleet/summary
        r_sum = self.client.get("/api/fleet/summary")
        self.assertEqual(r_sum.status_code, 200)
        sum_data = r_sum.json()
        self.assertIsInstance(sum_data["total_gems"], int)
        self.assertGreaterEqual(sum_data["captcha_alerts"], 1)

        # Query GET /fleet/summary (alternate alias)
        r_sum2 = self.client.get("/fleet/summary")
        self.assertEqual(r_sum2.status_code, 200)

        # Query GET /api/bot/DownstreamSafeBot
        r_bot = self.client.get("/api/bot/DownstreamSafeBot")
        self.assertEqual(r_bot.status_code, 200)
        bot_detail = r_bot.json()
        self.assertEqual(bot_detail["name"], "DownstreamSafeBot")
        self.assertEqual(bot_detail["captcha_status"], "solving")
        self.assertIsInstance(bot_detail["gems"], int)
        self.assertIsInstance(bot_detail["x"], int)
        self.assertIsInstance(bot_detail["y"], int)

        # Query GET /api/poll
        r_poll = self.client.get("/api/poll?bot=DownstreamSafeBot")
        self.assertEqual(r_poll.status_code, 200)
        poll_data = r_poll.json()
        self.assertEqual(poll_data["status"], "ok")
        self.assertEqual(poll_data["bot"], "DownstreamSafeBot")

    def test_batch_heartbeat_mixed_adversarial_constants(self):
        """
        Verify batch list heartbeat containing Infinity, -Infinity, NaN, and 'solving'
        across multiple bots in a single request.
        """
        batch = b"""[
            {"bot_name": "BatchBot_Inf", "captcha_status": Infinity, "gems": Infinity},
            {"bot_name": "BatchBot_NInf", "captcha_status": -Infinity, "gems": -Infinity},
            {"bot_name": "BatchBot_NaN", "captcha_status": NaN, "gems": NaN},
            {"bot_name": "BatchBot_Solving", "captcha_status": "solving", "gems": 1234},
            {"bot_name": "BatchBot_Normal", "captcha_status": "no_captcha", "gems": 4321}
        ]"""

        resp = self.client.post("/api/heartbeat", content=batch, headers={"Content-Type": "application/json"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("fleet_size"), 5)
        commands = data.get("commands", {})
        self.assertIn("BatchBot_Solving", commands)
        self.assertIn("BatchBot_Inf", commands)

        # Validate BotState in fleet_manager
        b_solv = fleet_manager.get_bot("BatchBot_Solving")
        self.assertIsNotNone(b_solv)
        self.assertEqual(b_solv.captcha_status, "solving")
        self.assertTrue(b_solv.has_captcha)
        self.assertEqual(b_solv.gem_count, 1234)

        b_inf = fleet_manager.get_bot("BatchBot_Inf")
        self.assertIsNotNone(b_inf)
        self.assertEqual(b_inf.captcha_status, "inf")
        self.assertFalse(b_inf.has_captcha)
        self.assertEqual(b_inf.gem_count, 0)

    def test_concurrent_burst_adversarial_heartbeats(self):
        """
        Concurrency challenge:
        30 threads concurrently firing heartbeat requests with alternating Infinity,
        -Infinity, NaN, and 'solving' for captcha_status.
        """
        iterations = 30
        results = []

        def worker(thread_idx: int):
            modes = [
                (b"Infinity", b"Infinity"),
                (b"-Infinity", b"-Infinity"),
                (b"NaN", b"NaN"),
                (b"\"solving\"", b"500"),
                (b"\"no_captcha\"", b"1000"),
            ]
            c_status, g_val = modes[thread_idx % len(modes)]
            bname = f"ConcBot_{thread_idx:02d}"
            body = (
                b'{"bot_name": "' + bname.encode() +
                b'", "captcha_status": ' + c_status +
                b', "gems": ' + g_val + b'}'
            )
            r = self.client.post("/api/heartbeat", content=body, headers={"Content-Type": "application/json"})
            return thread_idx, r.status_code, r.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(iterations)]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())

        self.assertEqual(len(results), iterations)
        for t_idx, status_code, body in results:
            self.assertEqual(status_code, 200, f"Thread {t_idx} failed with {status_code}: {body}")
            self.assertEqual(body.get("status"), "ok")


class TestBotManagerDirectAdversarialCoercion(unittest.TestCase):
    """Direct isolated unit tests for BotManager and BotState under adversarial edge cases."""

    def setUp(self):
        self.manager = BotManager()

    def test_direct_update_heartbeat_captcha_status_types(self):
        """
        Directly test update_heartbeat handles various types for captcha_status:
        - float('inf'), float('-inf'), float('nan')
        - string 'solving', 'wrong', 'failed'
        - None, int, dict, list
        """
        # Floats
        bot = self.manager.update_heartbeat({"bot_name": "DirectBot1", "captcha_status": float("inf")})
        self.assertEqual(bot.captcha_status, "inf")
        self.assertFalse(bot.has_captcha)

        bot = self.manager.update_heartbeat({"bot_name": "DirectBot2", "captcha_status": float("-inf")})
        self.assertEqual(bot.captcha_status, "-inf")
        self.assertFalse(bot.has_captcha)

        bot = self.manager.update_heartbeat({"bot_name": "DirectBot3", "captcha_status": float("nan")})
        self.assertEqual(bot.captcha_status, "nan")
        self.assertFalse(bot.has_captcha)

        # String 'solving'
        bot = self.manager.update_heartbeat({"bot_name": "DirectBot4", "captcha_status": "solving"})
        self.assertEqual(bot.captcha_status, "solving")
        self.assertTrue(bot.has_captcha)

        # None (should preserve default 'no_captcha')
        bot = self.manager.update_heartbeat({"bot_name": "DirectBot5", "captcha_status": None})
        self.assertEqual(bot.captcha_status, "no_captcha")
        self.assertFalse(bot.has_captcha)

        # Int (coerced to string)
        bot = self.manager.update_heartbeat({"bot_name": "DirectBot6", "captcha_status": 123})
        self.assertEqual(bot.captcha_status, "123")
        self.assertFalse(bot.has_captcha)

    def test_has_captcha_property_contract(self):
        """
        Verify all conditions that make BotState.has_captcha True or False.
        """
        # Default state
        state = BotState(name="TestState")
        self.assertFalse(state.has_captcha)

        # Triggered by captcha_status
        for active_status in ("solving", "wrong", "captcha_requested", "failed"):
            state.captcha_status = active_status
            self.assertTrue(state.has_captcha, f"Expected has_captcha=True for {active_status}")

        state.captcha_status = "no_captcha"
        self.assertFalse(state.has_captcha)

        # Triggered by status string
        state.status = "captcha_requested"
        self.assertTrue(state.has_captcha)
        state.status = "online"
        self.assertFalse(state.has_captcha)

        # Triggered by raw_status enum
        state.raw_status = BotStatus.CAPTCHA_REQUESTED
        self.assertTrue(state.has_captcha)
        state.raw_status = BotStatus.SOLVING_CAPTCHA
        self.assertTrue(state.has_captcha)
        state.raw_status = BotStatus.FAILED_CAPTCHA
        self.assertTrue(state.has_captcha)
        state.raw_status = BotStatus.ONLINE
        self.assertFalse(state.has_captcha)

    def test_captcha_alert_deduplication(self):
        """
        Verify that update_heartbeat only dispatches captcha_alert when captcha_status changes,
        preventing event spam.
        """
        alerts = []
        self.manager.subscribe_event(lambda evt, data: alerts.append((evt, data)))

        # First heartbeat with 'solving' -> triggers alert
        self.manager.update_heartbeat({"bot_name": "AlertDedupBot", "captcha_status": "solving"})
        self.assertEqual(len(alerts), 1)

        # Second heartbeat with 'solving' -> no state change, should NOT trigger another alert
        self.manager.update_heartbeat({"bot_name": "AlertDedupBot", "captcha_status": "solving"})
        self.assertEqual(len(alerts), 1)

        # Transition to 'wrong' -> state changed, triggers alert
        self.manager.update_heartbeat({"bot_name": "AlertDedupBot", "captcha_status": "wrong"})
        self.assertEqual(len(alerts), 2)

        # Transition to 'no_captcha' -> captcha cleared
        self.manager.update_heartbeat({"bot_name": "AlertDedupBot", "captcha_status": "no_captcha"})
        # No captcha_alert for clearing
        self.assertEqual(len(alerts), 2)


if __name__ == "__main__":
    unittest.main()
