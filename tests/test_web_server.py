"""
Tier 1, 3 & 4 Tests — Web Server & Relay Endpoints (FastAPI)
Tests FastAPI web server in web/server.py: static endpoints, /bridge.lua,
and interface contract validation for /api/heartbeat (POST) and /api/poll (GET).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient
from web.server import app
from core.bot_manager import fleet_manager


class TestWebServerSmoke(unittest.TestCase):
    """Tier 1: Smoke Tests for FastAPI Web Server."""

    def setUp(self):
        self.client = TestClient(app)

    def test_root_index_html(self):
        """Verify GET / returns 200 and loads the control deck dashboard."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("html", resp.headers.get("content-type", "").lower())

    def test_bridge_lua_endpoint(self):
        """Verify GET /bridge.lua serves the lua bridge script."""
        resp = self.client.get("/bridge.lua")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("LUCIFER", resp.text)
        self.assertIn("JSON", resp.text)

    def test_fleet_summary_endpoint(self):
        """Verify GET /api/fleet/summary returns JSON with fleet metrics."""
        resp = self.client.get("/api/fleet/summary")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_bots", data)
        self.assertIn("online_bots", data)


class TestWebRelayHeartbeatAndPollContracts(unittest.TestCase):
    """
    Tier 3: Relay Integration Contract Tests.
    Tests /api/heartbeat (POST) and /api/poll (GET) which are critical for bridge telemetry.
    ORIGINAL_REQUEST.md:161 identifies that /api/heartbeat and /api/poll were missing from web/server.py.
    """

    def setUp(self):
        self.client = TestClient(app)
        self.registered_routes = [route.path for route in app.routes]

    def test_api_heartbeat_route_registered(self):
        """
        Verify /api/heartbeat endpoint is registered in web/server.py.
        Bridge sends POST http://127.0.0.1:8829/api/heartbeat with bot telemetry.
        """
        if "/api/heartbeat" not in self.registered_routes:
            self.fail(
                "Defect Detected (Missing Relay Route): '/api/heartbeat' is NOT registered in web/server.py! "
                "Lucifer bridge calls to http://127.0.0.1:8829/api/heartbeat receive 404 Not Found."
            )

    def test_api_poll_route_registered(self):
        """
        Verify /api/poll endpoint is registered in web/server.py.
        Bridge sends GET http://127.0.0.1:8829/api/poll?bot=<name> to receive queued commands.
        """
        if "/api/poll" not in self.registered_routes:
            self.fail(
                "Defect Detected (Missing Relay Route): '/api/poll' is NOT registered in web/server.py! "
                "Lucifer bridge calls to http://127.0.0.1:8829/api/poll receive 404 Not Found."
            )

    def test_api_heartbeat_updates_fleet_manager(self):
        """Verify POST /api/heartbeat correctly updates fleet_manager and returns bot status."""
        if "/api/heartbeat" not in self.registered_routes:
            self.skipTest("Skipping payload test: /api/heartbeat not yet registered (Milestone 2 pending).")

        payload = {
            "bot_name": "TestBot_Beta",
            "status": 1,
            "world": "START",
            "x": 12,
            "y": 24,
            "gems": 1250,
            "level": 15,
            "ping": 45,
            "captcha": 0
        }
        resp = self.client.post("/api/heartbeat", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("bot"), "TestBot_Beta")
        self.assertIn("commands", data)

        # Verify fleet_manager state reflects heartbeat
        bot_state = fleet_manager.get_bot("TestBot_Beta")
        self.assertIsNotNone(bot_state)
        self.assertEqual(bot_state.world, "START")
        self.assertEqual(bot_state.gems, 1250)

    def test_api_poll_retrieves_queued_commands(self):
        """Verify GET /api/poll?bot=<name> retrieves commands from fleet_manager."""
        if "/api/poll" not in self.registered_routes:
            self.skipTest("Skipping poll test: /api/poll not yet registered (Milestone 2 pending).")

        bot_name = "PollTestBot"
        fleet_manager.queue_command(bot_name, "warp", {"world": "JAMMER"})

        resp = self.client.get(f"/api/poll?bot={bot_name}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        commands = data.get("commands", [])
        self.assertGreaterEqual(len(commands), 1)
        self.assertEqual(commands[0].get("action"), "warp")


class TestWebServerEdgeCases(unittest.TestCase):
    """Tier 4: Boundary & Malformed Request Tests."""

    def setUp(self):
        self.client = TestClient(app)
        self.registered_routes = [route.path for route in app.routes]

    def test_heartbeat_handles_empty_or_malformed_json(self):
        """Verify POST /api/heartbeat returns 400 or 422 on invalid/empty JSON."""
        if "/api/heartbeat" not in self.registered_routes:
            self.skipTest("/api/heartbeat route not yet registered.")

        resp = self.client.post(
            "/api/heartbeat",
            content="invalid-non-json-body",
            headers={"Content-Type": "application/json"}
        )
        self.assertIn(resp.status_code, (400, 422))

    def test_nonexistent_bot_poll_returns_empty_commands(self):
        """Verify GET /api/poll with unknown bot name returns empty command list gracefully."""
        if "/api/poll" not in self.registered_routes:
            self.skipTest("/api/poll route not yet registered.")

        resp = self.client.get("/api/poll?bot=GhostBot_NeverExisted")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("commands"), [])


if __name__ == "__main__":
    unittest.main()
