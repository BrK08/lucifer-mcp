"""
Adversarial Stress Harness for Milestone 1 (core/evren_client.py & run_discord_bot.py)
Executed by Challenger 1 (m1_challenger_1).

Tests boundary conditions, extreme multi-byte encodings, fuzz corpora,
regex injection, ReDoS vulnerabilities, and contract invariants.
"""
from __future__ import annotations

import asyncio
import os
import random
import string
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evren_client import (
    EvrenClient,
    EvrenAIClient,
    sanitize_lua_ascii,
    is_strict_ascii,
    validate_lua_ascii,
    detect_language,
    generate_script_slug,
)
try:
    import run_discord_bot
except ImportError:
    run_discord_bot = None


class TestAdversarialSanitizeLuaAscii(unittest.TestCase):
    """Stress testing sanitize_lua_ascii() with hostile and unusual unicode inputs."""

    def test_pure_ascii_unchanged(self):
        """Standard 7-bit ASCII code should pass through intact (except typographic quotes if any)."""
        code = "local bot = getBot()\nbot:say('Hello World!')\nsleep(200)\n"
        self.assertEqual(sanitize_lua_ascii(code), code)
        self.assertTrue(is_strict_ascii(sanitize_lua_ascii(code)))

    def test_turkish_character_transliteration_table(self):
        """Exhaustive check for Turkish lower & upper diacritics."""
        tr_chars = "çğıöşüÇĞİÖŞÜ"
        expected = "cgiosuCGIOSU"
        result = sanitize_lua_ascii(tr_chars, force_ascii=True)
        self.assertEqual(result, expected)
        self.assertTrue(is_strict_ascii(result))

    def test_circumflex_transliteration(self):
        """Circumflex accents common in Turkish loanwords."""
        circumflex = "âÂîÎûÛ"
        expected = "aAiIuU"
        result = sanitize_lua_ascii(circumflex, force_ascii=True)
        self.assertEqual(result, expected)
        self.assertTrue(is_strict_ascii(result))

    def test_typographic_punctuation_and_quotes(self):
        """Smart quotes, curly apostrophes, dashes, and ellipses."""
        text = "‘single’ “double” «guillemets» • bullet … dots – en — em − minus"
        expected = "'single' \"double\" \"guillemets\" - bullet ... dots - en -- em - minus"
        result = sanitize_lua_ascii(text, force_ascii=True)
        self.assertEqual(result, expected)
        self.assertTrue(is_strict_ascii(result))

    def test_non_standard_spaces(self):
        """Non-breaking space, zero-width space, narrow no-break space."""
        raw = "a\u00a0b\u200bc\u202fd"
        sanitized = sanitize_lua_ascii(raw, force_ascii=True)
        self.assertEqual(sanitized, "a bc d")
        self.assertTrue(is_strict_ascii(sanitized))

    def test_emojis_and_surrogate_pairs(self):
        """Emojis should be stripped cleanly without raising or leaving non-ASCII bytes."""
        emoji_code = 'bot:say("🔥 Bot Calisiyor! 🚀 💎 💯 🎮") -- 😀⚡'
        sanitized = sanitize_lua_ascii(emoji_code, force_ascii=True)
        self.assertTrue(is_strict_ascii(sanitized))
        self.assertNotIn("🔥", sanitized)
        self.assertNotIn("🚀", sanitized)
        self.assertIn("bot:say", sanitized)
        self.assertIn("Bot Calisiyor!", sanitized)

    def test_cyrillic_greek_cjk_arabic(self):
        """Non-Latin alphabets without direct ASCII decomposition must be stripped to preserve ASCII."""
        foreign = 'print("Привет мир / Γειά σου / 你好世界 / مرحبا")'
        sanitized = sanitize_lua_ascii(foreign, force_ascii=True)
        self.assertTrue(is_strict_ascii(sanitized))
        self.assertEqual(sanitized, 'print("  /   /  / ")')

    def test_combining_diacritical_marks_and_zalgo(self):
        """Combining marks decomposed via NFKD should have accents stripped while keeping base ASCII."""
        # e + combining acute (\u0301) -> e
        combining_e = "e\u0301"
        sanitized_e = sanitize_lua_ascii(combining_e, force_ascii=True)
        self.assertEqual(sanitized_e, "e")
        self.assertTrue(is_strict_ascii(sanitized_e))

        # Zalgo text (heavily stacked combining marks)
        zalgo = "T̸̛̤e̷̖̎s̸̱͝t̸͈͘"
        sanitized_zalgo = sanitize_lua_ascii(zalgo, force_ascii=True)
        self.assertEqual(sanitized_zalgo, "Test")
        self.assertTrue(is_strict_ascii(sanitized_zalgo))

    def test_empty_and_whitespace_strings(self):
        """Empty, newline-only, tab-only strings."""
        self.assertEqual(sanitize_lua_ascii("", force_ascii=True), "")
        self.assertEqual(sanitize_lua_ascii("\n\n\r\t  ", force_ascii=True), "\n\n\r\t  ")

    def test_large_lua_script_stress(self):
        """Stress with a 10,000-line Lua script with random Turkish and unicode insertions."""
        lines = [
            f"local var_{i} = 'değer_{i}_çüşğöı' -- Açıklama {i} • test"
            for i in range(10000)
        ]
        big_script = "\n".join(lines)
        sanitized = sanitize_lua_ascii(big_script, force_ascii=True)
        self.assertTrue(is_strict_ascii(sanitized))
        self.assertNotIn("ç", sanitized)
        self.assertNotIn("ğ", sanitized)
        self.assertNotIn("•", sanitized)
        self.assertIn("deger_0_cusgoi", sanitized)

    def test_random_fuzz_invariant(self):
        """Property-based invariant: for ANY random unicode string, result is 100% strict 7-bit ASCII."""
        rng = random.Random(42)
        for _ in range(500):
            # Generate random unicode characters across ranges (0x0000 to 0x10FFFF)
            chars = []
            for _ in range(50):
                cp = rng.choice([
                    rng.randint(0, 127),          # ASCII
                    rng.randint(128, 255),        # Latin-1 supplement
                    rng.randint(0x0100, 0x024F),  # Latin Extended
                    rng.randint(0x0400, 0x04FF),  # Cyrillic
                    rng.randint(0x1F600, 0x1F64F),# Emojis
                    rng.randint(0x0300, 0x036F),  # Combining diacritics
                ])
                try:
                    chars.append(chr(cp))
                except ValueError:
                    continue
            raw_str = "".join(chars)
            sanitized = sanitize_lua_ascii(raw_str, force_ascii=True)
            self.assertTrue(
                is_strict_ascii(sanitized),
                f"Fuzz failure: non-ASCII byte leaked from input {raw_str!r}: {sanitized!r}"
            )


class TestAdversarialDetectLanguage(unittest.TestCase):
    """Stress testing detect_language() with boundary, mixed, and ambiguous inputs."""

    def test_empty_and_falsy(self):
        """Empty string or None should safely default to 'tr'."""
        self.assertEqual(detect_language(""), "tr")
        self.assertEqual(detect_language(None), "tr")

    def test_distinctive_turkish_characters(self):
        """Any presence of ç, ğ, ı, ö, ş, ü immediately determines 'tr'."""
        self.assertEqual(detect_language("Ağaç"), "tr")
        self.assertEqual(detect_language("ışık"), "tr")
        self.assertEqual(detect_language("çiftlik"), "tr")
        self.assertEqual(detect_language("Script hazırla"), "tr")
        self.assertEqual(detect_language("Write code for me lütfen"), "tr")

    def test_ascii_turkish_without_diacritics(self):
        """Turkish written with ASCII letters only (no diacritics)."""
        self.assertEqual(detect_language("bana bir farm scripti yaz lutfen"), "tr")
        self.assertEqual(detect_language("dunya icinde esyalari topla"), "tr")
        self.assertEqual(detect_language("bot neden calismiyor hata verdi"), "tr")

    def test_clear_english_commands(self):
        """Standard English commands for script generation."""
        self.assertEqual(detect_language("write a script to collect seeds in the farm world"), "en")
        self.assertEqual(detect_language("how to make the bot enter the door?"), "en")
        self.assertEqual(detect_language("please fix this error when harvesting chandelier"), "en")
        self.assertEqual(detect_language("create auto farm code for laser grid"), "en")

    def test_ambiguous_and_symbolic_inputs(self):
        """Inputs with zero linguistic keywords default gracefully to 'tr'."""
        self.assertEqual(detect_language("123456 789"), "tr")
        self.assertEqual(detect_language("!@#$%^&*()_+"), "tr")
        self.assertEqual(detect_language("xyz abc qqq"), "tr")
        self.assertEqual(detect_language("   \n\t  "), "tr")

    def test_english_command_mentioning_turkish_world_name(self):
        """English command targeting a Turkish world name."""
        prompt = "write a script to warp to world ASLAN and harvest plants"
        self.assertEqual(detect_language(prompt), "en")

    def test_single_word_queries(self):
        """Edge case: 1-word inputs."""
        self.assertEqual(detect_language("farm"), "en")
        self.assertEqual(detect_language("write"), "en")
        self.assertEqual(detect_language("topla"), "tr")
        self.assertEqual(detect_language("yardim"), "tr")
        self.assertEqual(detect_language("bot"), "tr")  # tied (bot in both), defaults to tr


class TestAdversarialGenerateScriptSlug(unittest.TestCase):
    """Stress testing generate_script_slug() with regex injection, long strings, and edge cases."""

    def test_empty_and_falsy_prompts(self):
        """Empty string or None must return valid .lua filename."""
        self.assertEqual(generate_script_slug(""), "lucifer_script.lua")
        self.assertEqual(generate_script_slug(None), "lucifer_script.lua")
        self.assertEqual(generate_script_slug("   \t\n  "), "lucifer_script.lua")

    def test_target_world_extraction_patterns(self):
        """Extract world name according to user phrasing."""
        # ORIGINAL_REQUEST.md:24 exact prompt
        p1 = "asdsadasdasd adındaki dünyaya giren bir script hazırla"
        self.assertEqual(generate_script_slug(p1), "asdsadasdasd_auto_warp.lua")

        p2 = "FARMWORLD123 adlı dünyada dirt farm yap"
        self.assertEqual(generate_script_slug(p2), "farmworld123_dirt_auto_farm.lua")

        p3 = "myworld world enter"
        self.assertEqual(generate_script_slug(p3), "myworld_auto_warp.lua")

    def test_item_and_action_combinations(self):
        """Item and action keywords correctly recognized and assembled."""
        self.assertEqual(generate_script_slug("dirt topla"), "dirt_auto_collect.lua")
        self.assertEqual(generate_script_slug("sugar cane ek ve hasat et"), "sugar_cane_auto_farm.lua")
        self.assertEqual(generate_script_slug("laser grid pnb"), "laser_grid_pnb.lua")
        self.assertEqual(generate_script_slug("chandelier kır"), "chandelier_pnb.lua")
        self.assertEqual(generate_script_slug("balık tut"), "auto_fish.lua")
        self.assertEqual(generate_script_slug("geiger taraması yap"), "geiger_auto_geiger.lua")

    def test_special_characters_and_sql_regex_injection(self):
        """Adversarial prompt characters (quotes, backslashes, regex meta-characters)."""
        prompt = ".*+?^${}()|[]\\ ' OR 1=1; DROP TABLE scripts; -- /etc/passwd"
        slug = generate_script_slug(prompt)
        self.assertTrue(slug.endswith(".lua"))
        # Must only contain a-z, 0-9, _, .
        self.assertRegex(slug, r"^[a-zA-Z0-9_]+\.lua$")
        self.assertNotIn("/", slug)
        self.assertNotIn("..", slug)
        self.assertNotIn("'", slug)

    def test_massive_prompt_redos_resistance(self):
        """Verify regex does not catastrophically backtrack on huge repetitive inputs."""
        massive_prompt = ("a" * 50000) + " adındaki dünyaya giren script " + ("b" * 50000)
        slug = generate_script_slug(massive_prompt)
        self.assertTrue(slug.endswith(".lua"))
        self.assertRegex(slug, r"^[a-zA-Z0-9_]+\.lua$")

    def test_item_hint_as_code_swap(self):
        """If caller passes code as 2nd parameter, function detects multiline/getBot and swaps gracefully."""
        code = "local bot = getBot()\nbot:say('test')"
        slug = generate_script_slug("dirt farm", item_hint=code)
        self.assertEqual(slug, "dirt_auto_farm.lua")

    def test_item_hint_formatting(self):
        """Item hints with IDs like 'Dirt (2)' or 'Laser Grid (5666)' formatted cleanly."""
        slug = generate_script_slug("farm yap", item_hint="Laser Grid (5666)")
        self.assertEqual(slug, "laser_grid_auto_farm.lua")

    def test_slug_is_never_empty_filename(self):
        """Slug must never be '.lua' or empty."""
        for strange in ["???", "---", "___", "!!!", "1", "a", "@#$"]:
            slug = generate_script_slug(strange)
            self.assertTrue(slug.endswith(".lua"))
            self.assertGreater(len(slug), 4)
            self.assertRegex(slug, r"^[a-zA-Z0-9_]+\.lua$")


class TestAdversarialResolveAiConfig(unittest.TestCase):
    """Stress testing resolve_ai_config() in run_discord_bot.py."""

    def setUp(self):
        if run_discord_bot is None:
            self.skipTest("Private run_discord_bot module not present in public MCP repo")

    def test_standard_ai_dict(self):
        """Standard 'ai' dictionary returned cleanly."""
        cfg = {"ai": {"project_id": "pid-1", "model": "auto"}}
        self.assertEqual(run_discord_bot.resolve_ai_config(cfg), {"project_id": "pid-1", "model": "auto"})

    def test_fallback_to_evren_ai_dict(self):
        """Fallback to 'evren_ai' dictionary when 'ai' is missing."""
        cfg = {"evren_ai": {"project_id": "pid-2", "model": "gemini"}}
        self.assertEqual(run_discord_bot.resolve_ai_config(cfg), {"project_id": "pid-2", "model": "gemini"})

    def test_ai_key_is_none_falls_back_to_evren_ai(self):
        """CRITICAL: If 'ai' is None, must fallback to 'evren_ai' instead of crashing with AttributeError."""
        cfg = {"ai": None, "evren_ai": {"project_id": "pid-fallback"}}
        self.assertEqual(run_discord_bot.resolve_ai_config(cfg), {"project_id": "pid-fallback"})

    def test_both_ai_and_evren_ai_none(self):
        """Both sections present but None."""
        cfg = {"ai": None, "evren_ai": None}
        self.assertEqual(run_discord_bot.resolve_ai_config(cfg), {})

    def test_empty_config_dict(self):
        """Empty dictionary."""
        self.assertEqual(run_discord_bot.resolve_ai_config({}), {})

    def test_corrupted_types_in_config(self):
        """Non-dict values under 'ai' and 'evren_ai' (strings, lists, ints, booleans)."""
        for bad_val in ["string_corrupted", [1, 2, 3], 9999, True]:
            cfg1 = {"ai": bad_val}
            self.assertEqual(run_discord_bot.resolve_ai_config(cfg1), {})
            cfg2 = {"ai": bad_val, "evren_ai": bad_val}
            self.assertEqual(run_discord_bot.resolve_ai_config(cfg2), {})


class TestAdversarialEvrenClientChatContract(unittest.TestCase):
    """Stress testing EvrenClient.chat() unified interface contract."""

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="mock_key")

    def test_chat_returns_exact_contract_keys(self):
        """Verify chat() returns dict with {'text', 'code', 'slug', 'model'}."""
        mock_raw = (
            "Harika! İşte istediğiniz script:\n\n"
            "```lua\n"
            'bot:say("Ağaç büyüdü!")\n'
            "```\n\n"
            "Dünyadaki ağaçlar başarıyla toplanacak."
        )
        with patch.object(self.client, "chat_completion", new=AsyncMock(return_value=mock_raw)):
            res = asyncio.run(self.client.chat("asdsadasdasd dünyasına giren script yaz"))
            self.assertIsInstance(res, dict)
            self.assertEqual(set(res.keys()), {"text", "code", "slug", "model"})

            # 'code' must be strict ASCII
            self.assertTrue(is_strict_ascii(res["code"]))
            self.assertIn('bot:say("Agac buyudu!")', res["code"])
            self.assertNotIn("Ağaç", res["code"])

            # 'text' outside block must retain Turkish characters
            self.assertIn("Harika! İşte istediğiniz script:", res["text"])
            self.assertIn("Dünyadaki ağaçlar başarıyla toplanacak.", res["text"])

            # 'slug' must be non-empty and end in .lua
            self.assertTrue(res["slug"].endswith(".lua"))
            self.assertEqual(res["slug"], "asdsadasdasd_auto_warp.lua")

    def test_chat_with_pure_conversational_query_no_code(self):
        """When query is a question without Lua code, 'code' and 'slug' should be empty, not crash."""
        mock_raw = "Lucifer v2.88 p2 botunda status 22 moderatör girişini temsil eder."
        with patch.object(self.client, "chat_completion", new=AsyncMock(return_value=mock_raw)):
            res = asyncio.run(self.client.chat("status 22 nedir?"))
            self.assertEqual(res["code"], "")
            self.assertEqual(res["slug"], "")
            self.assertIn("status 22 moderatör", res["text"])


class TestAdversarialValidateLuaAscii(unittest.TestCase):
    """Stress testing validate_lua_ascii() helper."""

    def test_pure_ascii_validates_cleanly(self):
        """Pure ASCII returns (True, [])."""
        valid, violations = validate_lua_ascii("local bot = getBot()\nbot:say('OK')\n")
        self.assertTrue(valid)
        self.assertEqual(len(violations), 0)

    def test_violations_report_exact_coordinates(self):
        """Violations list contains correct line, column, and codepoint."""
        text = "local x = 1\nlocal name = 'Ağaç'\n"
        valid, violations = validate_lua_ascii(text)
        self.assertFalse(valid)
        self.assertEqual(len(violations), 2)  # 'ğ' and 'ç'
        self.assertEqual(violations[0]["line"], 2)
        self.assertEqual(violations[0]["char"], "ğ")
        self.assertEqual(violations[0]["codepoint"], "U+011F")
        self.assertEqual(violations[1]["line"], 2)
        self.assertEqual(violations[1]["char"], "ç")
        self.assertEqual(violations[1]["codepoint"], "U+00E7")


class TestAdversarialSystemPromptAndDocsIntegrity(unittest.TestCase):
    """Stress testing prompt content and training doc for prohibited hallucinated methods."""

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="mock_key")

    def test_system_prompt_strictly_bans_hallucinations(self):
        """Verify build_system_prompt() bans bot:getBotStatus(), world:getDoors(), world:name(), / 32."""
        prompt = self.client.build_system_prompt("general")

        # Prohibitions
        self.assertIn("bot.status is an INTEGER PROPERTY", prompt)
        self.assertIn("CRITICAL: bot:getBotStatus() DOES NOT EXIST", prompt)
        self.assertIn("world:getDoors() DOES NOT EXIST", prompt)
        self.assertIn("world.name is a STRING PROPERTY", prompt)
        self.assertIn("NEVER write world:name()", prompt)
        self.assertIn("DO NOT divide by 32", prompt)

        # Verified methods present
        self.assertIn("bot:place(x, y, item_id)", prompt)
        self.assertIn("bot:warp(world, door_id)", prompt)
        self.assertIn("if bot.status == 22 then", prompt)
        self.assertIn("if bot.status == 43 then", prompt)

    def test_docs_do_not_instruct_prohibited_methods_in_code_blocks(self):
        """Check docs/AI_TRAINING_LUCIFER.md to ensure no lua code blocks instruct hallucinated methods."""
        docs_path = ROOT / "docs" / "AI_TRAINING_LUCIFER.md"
        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Prohibited methods must NEVER appear inside ```lua ... ``` blocks
        import re
        code_blocks = re.findall(r"```(?:lua)?\s*\n(.*?)```", content, flags=re.DOTALL)
        for idx, block in enumerate(code_blocks):
            self.assertNotIn("bot:getBotStatus()", block, f"Code block {idx} contains bot:getBotStatus()")
            self.assertNotIn("world:getDoors()", block, f"Code block {idx} contains world:getDoors()")
            self.assertNotIn("world:name()", block, f"Code block {idx} contains world:name()")

        # Prohibitions documented in Hallucination Traps section
        self.assertIn("bot:getBotStatus()` YASAK", content)
        self.assertIn("world:getDoors()` YASAK", content)
        self.assertIn("world:name()` YASAK", content)

        # Verified in code
        self.assertIn("if bot.status == 22 then", content)
        self.assertIn("if bot.status == 43 then", content)


if __name__ == "__main__":
    unittest.main()

