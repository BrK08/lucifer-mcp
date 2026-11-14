"""
Lucifer Multibot — Auto-Test & Self-Learning Engine
Enables AI to execute generated Lua scripts in real-time, inspect live logs from
Lucifer's [Logs] console tab, detect runtime errors, automatically synthesize patches,
and persist learned bug patterns to memory (data/learned_patterns.json).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from core.bot_manager import fleet_manager
from core.evren_client import evren_client, sanitize_lua_ascii

PATTERNS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "learned_patterns.json")

# Common Growtopia / Lucifer Lua runtime error patterns
ERROR_PATTERNS = [
    r"\[Script Error\]\s*(.*)",
    r"\[Script Syntax Error\]\s*(.*)",
    r"attempt to index a (?:number|nil|boolean) value",
    r"attempt to call a nil value",
    r"attempt to call global '(\w+)'",
    r"bad argument #\d+ to '(\w+)'",
    r"error in error handling",
    r"stack overflow",
    r"syntax error near '(\w+)'",
    r"unexpected symbol near '([^']+)'",
]


class AutoTester:
    def __init__(self):
        self.learned_patterns: List[Dict[str, Any]] = []
        self._load_patterns()

    def _load_patterns(self):
        if os.path.exists(PATTERNS_FILE):
            try:
                with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
                    self.learned_patterns = json.load(f)
            except Exception as e:
                print(f"[AutoTester] Failed to load learned patterns: {e}")
                self.learned_patterns = []

    def save_learned_pattern(self, bug_type: str, error_msg: str, bad_code_snippet: str, fixed_snippet: str):
        """Persists a new bug & fix pair to the learned patterns memory."""
        pattern = {
            "timestamp": time.time(),
            "bug_type": bug_type,
            "error_msg": error_msg.strip(),
            "bad_snippet": bad_code_snippet.strip()[:300],
            "fixed_snippet": fixed_snippet.strip()[:300],
        }
        self.learned_patterns.append(pattern)
        try:
            os.makedirs(os.path.dirname(PATTERNS_FILE), exist_ok=True)
            with open(PATTERNS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.learned_patterns[-100:], f, indent=2, ensure_ascii=False)
            print(f"[AutoTester] Saved new learned pattern for: {bug_type}")
        except Exception as e:
            print(f"[AutoTester] Failed to save pattern: {e}")

    def detect_errors_in_log(self, log_text: str) -> Optional[str]:
        """Scans log content for Lua errors or crashes."""
        if not log_text:
            return None
        for pattern in ERROR_PATTERNS:
            match = re.search(pattern, log_text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None

    async def execute_and_verify(
        self,
        lua_code: str,
        bot_name: str = "all",
        wait_seconds: float = 2.5,
    ) -> Dict[str, Any]:
        """
        Executes Lua code on target bot, waits for execution, reads the [Logs] feed,
        and if an error occurs, automatically patches the script and learns from it.
        """
        clean_code = sanitize_lua_ascii(lua_code)

        # Select target bot
        bots = fleet_manager.list_bots()
        target_bot = None
        if bot_name.lower() in ("all", "global", "first"):
            target_bot = bots[0] if bots else None
        else:
            target_bot = fleet_manager.get_bot(bot_name)

        if not target_bot:
            return {
                "success": False,
                "error": f"No active bot found matching '{bot_name}'. Please ensure Lucifer is running with lucifer_bridge.lua.",
                "original_code": clean_code,
            }

        # Dispatch code to bot
        cmd_id = fleet_manager.queue_command(target_bot.name, "run_script", {"code": clean_code})

        # Wait for Lucifer to execute and capture logs
        await asyncio.sleep(wait_seconds)

        # Read latest logs from bot
        current_logs = target_bot.raw_info.get("logs", "")

        # Inspect logs for script errors
        error_found = self.detect_errors_in_log(current_logs)

        if error_found:
            # Self-Correction: Ask EVREN to fix the code using live error
            fixed_response = await evren_client.fix_script(
                code_or_error=clean_code,
                error_context=f"Live Lucifer v2.88 p2 runtime log captured error: '{error_found}'",
            )

            # Extract clean fixed Lua block
            fixed_code = clean_code
            m = re.search(r"```lua\n(.*?)```", fixed_response, flags=re.DOTALL)
            if m:
                fixed_code = sanitize_lua_ascii(m.group(1))

            # Store what we learned
            self.save_learned_pattern(
                bug_type="runtime_error",
                error_msg=error_found,
                bad_code_snippet=clean_code,
                fixed_snippet=fixed_code,
            )

            return {
                "success": False,
                "status": "error_detected_and_auto_patched",
                "error_detected": error_found,
                "bot": target_bot.name,
                "recent_logs": current_logs[-800:] if current_logs else "",
                "original_code": clean_code,
                "fixed_code": fixed_code,
                "explanation": fixed_response,
            }

        return {
            "success": True,
            "status": "verified_working",
            "bot": target_bot.name,
            "recent_logs": current_logs[-800:] if current_logs else "",
            "executed_code": clean_code,
        }


auto_tester = AutoTester()
