"""
Tier 1, 2, 3 & 4 Tests — Evren AI Client, Prompt Engineering & Lua Sanitization
Verifies prompt generation, strictly bans bot:getBotStatus(), enforces bot.status property,
validates bilingual directives, and tests pure ASCII sanitization for Growtopia Lua.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.evren_client import EvrenClient, sanitize_lua_ascii


class TestEvrenClientSmokeAndSanitization(unittest.TestCase):
    """Tier 1: Smoke & String Sanitization Tests."""

    def test_client_default_initialization(self):
        """Verify EvrenClient instantiates with expected defaults when isolated from config file."""
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            client = EvrenClient(api_key="test_key_abc", base_url="https://api.test/v1")
            self.assertEqual(client.base_url, "https://api.test/v1")
            self.assertEqual(client.api_key, "test_key_abc")
            self.assertTrue(client.is_configured)

    def test_sanitize_lua_ascii_replaces_all_turkish_glyphs(self):
        """Verify sanitize_lua_ascii replaces all Turkish characters with ASCII."""
        raw_lua = 'bot:say("Ağaç büyüdü, çilek toplandı, ışık açıldı, şelale gördük, ördek yüzdü.")'
        sanitized = sanitize_lua_ascii(raw_lua)
        
        # Growtopia font unsupported characters must be gone
        for forbidden in ["ğ", "Ğ", "ü", "Ü", "ş", "Ş", "ı", "İ", "ö", "Ö", "ç", "Ç"]:
            self.assertNotIn(forbidden, sanitized, f"Found unsanitized Turkish character '{forbidden}'")
        
        self.assertIn('bot:say("Agac buyudu, cilek toplandi, isik acildi, selale gorduk, ordek yuzdu.")', sanitized)

    def test_sanitize_lua_ascii_handles_special_symbols(self):
        """Verify quotes and bullets are sanitized for Lua execution."""
        raw = "• Item ‘quoted’ and “double” … ellipsis"
        sanitized = sanitize_lua_ascii(raw)
        self.assertNotIn("•", sanitized)
        self.assertNotIn("…", sanitized)
        self.assertIn("- Item 'quoted' and \"double\" ... ellipsis", sanitized)


class TestEvrenClientPromptSpecification(unittest.TestCase):
    """
    Tier 2 / Tier 3: Zero-Hallucination Prompt Verification Tests.
    Ensures bot:getBotStatus() is absent, bot.status property is taught, and ASCII rules enforced.
    """

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="mock_key")

    def test_prompt_does_not_contain_bot_getBotStatus_method(self):
        """
        CRITICAL TEST (ORIGINAL_REQUEST.md:25, 69):
        Verify that 'bot:getBotStatus()' is completely eliminated from the system prompt.
        Previously, evren_client.py:155 taught: 'if bot.status == 22 or bot:getBotStatus() == 22 then'.
        """
        prompt = self.client.build_system_prompt("general")
        
        # Check if the hallucinated method is recommended
        # Note: If mentioned as a forbidden rule (e.g. "NEVER use bot:getBotStatus()"), that is allowed,
        # but it must NOT be instructed as valid code.
        positive_usage = "or bot:getBotStatus() ==" in prompt or "bot:getBotStatus() == 22" in prompt
        self.assertFalse(
            positive_usage,
            "CRITICAL DEFECT: System prompt teaches 'bot:getBotStatus() == 22'. "
            "bot:getBotStatus() does not exist in Lucifer v2.88 p2 runtime and causes fatal nil call error!"
        )

    def test_prompt_teaches_bot_status_property(self):
        """Verify prompt teaches bot.status as a number property."""
        prompt = self.client.build_system_prompt("general")
        self.assertIn("bot.status", prompt, "System prompt must teach 'bot.status' property.")

    def test_prompt_teaches_humanized_jitter_delays(self):
        """Verify prompt enforces randomized delays rather than static sleep."""
        prompt = self.client.build_system_prompt("script_generation")
        self.assertIn("math.random", prompt)
        self.assertIn("jitter", prompt.lower())

    def test_prompt_teaches_anti_ban_delays_and_moderator_evasion(self):
        """Verify prompt contains mod evasion (status 22) and banwave (status 43) protocols."""
        prompt = self.client.build_system_prompt("general")
        self.assertIn("22", prompt)
        self.assertIn("43", prompt)

    def test_prompt_warns_against_dividing_coordinates_by_32(self):
        """Verify prompt instructs that bot.x and bot.y are already tile coordinates."""
        prompt = self.client.build_system_prompt("general")
        self.assertIn("32", prompt)
        self.assertIn("tile coordinates", prompt.lower())


class TestEvrenClientPostProcessing(unittest.TestCase):
    """Tier 2 / Tier 3: Post-processing and Markdown Code Extraction."""

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="mock_key")

    def test_post_process_sanitizes_lua_blocks_only(self):
        """
        Verify that post-processing sanitizes Lua code blocks to ASCII,
        while strictly PRESERVING Turkish characters in conversational text outside the block!
        """
        raw_response = (
            "Merhaba! İstediğiniz script aşağıdadır:\n\n"
            "```lua\n"
            'bot:say("Ağaç büyüdü!")\n'
            "```\n\n"
            "Bu kod ile dünyadaki ağaçları otomatik toplayabilirsiniz. Şansınız bol olsun!"
        )

        processed = self.client._post_process_script_response(raw_response)

        # Conversational text outside code block MUST preserve Turkish characters
        self.assertIn("Merhaba! İstediğiniz script aşağıdadır:", processed)
        self.assertIn("dünyadaki ağaçları otomatik toplayabilirsiniz. Şansınız bol olsun!", processed)

        # Inside code block MUST be sanitized to ASCII
        self.assertIn('bot:say("Agac buyudu!")', processed)
        self.assertNotIn('bot:say("Ağaç büyüdü!")', processed)

    def test_post_process_adds_watermark_header(self):
        """Verify generated scripts receive repository watermark header."""
        raw_response = "```lua\nlocal bot = getBot()\n```"
        processed = self.client._post_process_script_response(raw_response)
        self.assertIn("Made by", processed)
        self.assertIn("github.com/BrK08/lucifer-mcp", processed)


class TestEvrenClientNetworkErrorHandling(unittest.TestCase):
    """Tier 4: Concurrency, Quota & Network Resilience Tests."""

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="test_valid_key")

    def test_chat_completion_unconfigured_error(self):
        """Verify helpful error message when API key is not configured."""
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            unconfigured_client = EvrenClient(api_key="")
            unconfigured_client.api_key = ""
            result = asyncio.run(unconfigured_client.chat_completion([{"role": "user", "content": "hi"}]))
            self.assertIn("AI API Anahtarı Tanımlanmamış", result)

    def test_chat_completion_handles_429_quota_limit(self):
        """Verify HTTP 429 rate-limiting response provides user-friendly warning."""
        mock_resp = AsyncMock()
        mock_resp.status = 429

        mock_session = MagicMock()
        mock_session.post.return_value.__aenter__.return_value = mock_resp
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("aiohttp.ClientSession", return_value=mock_session), \
             patch.object(self.client, "ensure_terms_accepted", new=AsyncMock(return_value=True)):
            result = asyncio.run(self.client.chat_completion([{"role": "user", "content": "test"}]))
            self.assertIn("429", result)
            self.assertIn("Kota Limiti", result)

    def test_chat_completion_handles_401_unauthorized(self):
        """Verify HTTP 401 returns clear authentication error."""
        mock_resp = AsyncMock()
        mock_resp.status = 401

        mock_session = MagicMock()
        mock_session.post.return_value.__aenter__.return_value = mock_resp
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("aiohttp.ClientSession", return_value=mock_session), \
             patch.object(self.client, "ensure_terms_accepted", new=AsyncMock(return_value=True)):
            result = asyncio.run(self.client.chat_completion([{"role": "user", "content": "test"}]))
            self.assertIn("401", result)
            self.assertIn("Yetkilendirme Hatası", result)

    def test_chat_completion_handles_timeout(self):
        """Verify asyncio.TimeoutError is caught and formatted."""
        mock_session = MagicMock()
        mock_session.post.side_effect = asyncio.TimeoutError()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with patch("aiohttp.ClientSession", return_value=mock_session), \
             patch.object(self.client, "ensure_terms_accepted", new=AsyncMock(return_value=True)):
            try:
                result = asyncio.run(self.client.chat_completion([{"role": "user", "content": "test"}]))
                self.assertIn("Zaman Aşımı", result)
            except NameError as e:
                self.fail(f"Defect Detected in core/evren_client.py: {e}. Missing 'import asyncio' in evren_client.py!")


if __name__ == "__main__":
    unittest.main()
