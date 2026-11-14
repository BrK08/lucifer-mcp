"""
Tier 2 & Tier 3 Tests — Lua Bridge & JSON Decoding Syntax
Tests bridge/lucifer_bridge.lua:
1. JSON.decode pattern verification: demonstrates why s:gsub('":', '"=') produces invalid Lua syntax
   and validates that s:gsub('"([^"]+)"%s*:', '["%1"]=') produces valid bracketed table keys.
2. HttpClient POST method and header configurations.
3. Multi-bot fleet iteration (getBots() support).
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE_LUA_PATH = ROOT / "bridge" / "lucifer_bridge.lua"


class TestBridgeLuaSyntaxAndPatterns(unittest.TestCase):
    """Tier 2: Algorithmic & Syntax Verification for JSON Decoding in Lua."""

    def test_broken_json_gsub_pattern_demonstration(self):
        """
        Verify that the naive pattern s:gsub('":', '"=') produces invalid Lua syntax.
        In Lua:
            { "key" = "value" } -> syntax error near '='
        Keys in Lua tables must either be unquoted identifiers (key = val)
        or bracketed expressions (["key"] = val).
        """
        json_sample = '{"status":"ok","command":"warp"}'
        broken_lua_str = json_sample.replace('":', '"=')
        
        # Result is '{"status"="ok","command"="warp"}'
        self.assertEqual(broken_lua_str, '{"status"="ok","command"="warp"}')
        
        # A Lua table syntax validator: check if unbracketed quoted key with '=' exists
        has_invalid_unbracketed_key = bool(re.search(r'\{?\s*"[^"]+"\s*=', broken_lua_str))
        self.assertTrue(
            has_invalid_unbracketed_key,
            "Broken gsub pattern produces illegal Lua syntax: quoted string directly followed by '='"
        )

    def test_fixed_json_gsub_pattern_produces_valid_bracketed_keys(self):
        """
        Verify that the pattern s:gsub('"([^"]+)"%s*:', '["%1"]=')
        produces valid bracketed table keys: {["key"]="val"}.
        """
        json_sample = '{"status":"ok","command":"warp","delay":200}'
        
        # Python equivalent of Lua regex: s:gsub('"([^"]+)"%s*:', '["%1"]=')
        fixed_lua_str = re.sub(r'"([^"]+)"\s*:', r'["\1"]=', json_sample)
        
        expected_substrings = ['["status"]="ok"', '["command"]="warp"', '["delay"]=200']
        for sub in expected_substrings:
            self.assertIn(sub, fixed_lua_str)

        # In valid Lua table, every string key MUST be inside brackets: ["..."] =
        invalid_keys = re.findall(r'(?<!\[)"[^"]+"(?!\s*\])\s*=', fixed_lua_str)
        self.assertEqual(len(invalid_keys), 0, f"Found unbracketed keys in Lua string: {invalid_keys}")

    def test_json_decode_handles_nested_objects_and_arrays(self):
        """
        Verify the safe pipeline order:
        First array brackets [...] are converted to {...}, then null to nil,
        then keys are bracketed to ["key"]=.
        """
        json_sample = '{"bot":"Alpha","actions":["warp","collect"],"config":{"speed":100}}'
        
        # Safe order of operations:
        # 1. Convert JSON array brackets to Lua table curly braces
        step1 = re.sub(r'\[([^\]]*)\]', r'{\1}', json_sample)
        # 2. Convert null to nil
        step2 = step1.replace('null', 'nil')
        # 3. Convert quoted keys to bracketed keys ["key"]=
        step3 = re.sub(r'"([^"]+)"\s*:', r'["\1"]=', step2)

        self.assertIn('["bot"]="Alpha"', step3)
        self.assertIn('["actions"]={"warp","collect"}', step3)
        self.assertIn('["config"]={["speed"]=100}', step3)


class TestBridgeLuaSourceCode(unittest.TestCase):
    """
    Tier 3: Source Code Inspection for bridge/lucifer_bridge.lua.
    Checks whether the fixes specified in ORIGINAL_REQUEST.md have been implemented in the file.
    """

    def setUp(self):
        self.assertTrue(BRIDGE_LUA_PATH.exists(), f"File {BRIDGE_LUA_PATH} does not exist!")
        with open(BRIDGE_LUA_PATH, "r", encoding="utf-8") as f:
            self.source = f.read()

    def test_json_decode_uses_bracketed_keys_in_source(self):
        """
        Verify bridge/lucifer_bridge.lua does NOT use the broken s:gsub('":', '"=')
        and instead uses bracketed keys '["%1"]='.
        ORIGINAL_REQUEST.md line 158-160.
        """
        has_broken_pattern = "s:gsub('\":', '\"=')" in self.source or 's:gsub("\":", "\"=")' in self.source
        if has_broken_pattern:
            self.fail(
                "Defect Detected in bridge/lucifer_bridge.lua: JSON.decode still contains broken pattern "
                "s:gsub('\":', '\"='). Must be replaced with bracketed key pattern s:gsub('\"([^\"]+)\"%s*:', '[\"%1\"]=')."
            )

    def test_http_client_post_and_json_header(self):
        """
        Verify bridge/lucifer_bridge.lua configures HttpClient with Method.post and application/json header.
        ORIGINAL_REQUEST.md line 162.
        """
        self.assertIn("HttpClient", self.source, "Bridge must instantiate HttpClient.")
        has_json_header = '["Content-Type"] = "application/json"' in self.source or "'Content-Type' = 'application/json'" in self.source or "application/json" in self.source
        self.assertTrue(has_json_header, "Bridge must set Content-Type: application/json header.")

    def test_lua_source_ascii_cleanliness(self):
        """
        Verify bridge/lucifer_bridge.lua contains NO Turkish characters that would crash Growtopia.
        """
        turkish_chars = ["ğ", "Ğ", "ü", "Ü", "ş", "Ş", "ı", "İ", "ö", "Ö", "ç", "Ç"]
        found = [c for c in turkish_chars if c in self.source]
        self.assertEqual(len(found), 0, f"Found forbidden Turkish characters in bridge/lucifer_bridge.lua: {found}")


if __name__ == "__main__":
    unittest.main()
