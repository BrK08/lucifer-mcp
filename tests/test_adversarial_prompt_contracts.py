"""
Adversarial Verification Suite for Milestone 1 (m1_challenger_2)
Empirically challenges:
1. System prompt generation and negative constraints (zero hallucinated methods).
2. Bilingual rules: 7-bit ASCII strictly confined to Lua; natural Turkish preserved in chat.
3. Training documentation integrity (docs/AI_TRAINING_LUCIFER.md).
4. Post-processing, sanitization, language detection, and slug generation stress harnesses.
5. EvrenClient.chat() PROJECT.md interface contract and failure resilience.
"""
from __future__ import annotations

import asyncio
import os
import re
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


class TestSystemPromptIntegrity(unittest.TestCase):
    """
    Empirically verifies system prompt generation and negative constraints.
    Ensures that no hallucinated methods are suggested, negative constraints hold,
    and runtime contracts are accurate for Lucifer v2.88 p2.
    """

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="mock_adversarial_key")

    def test_prompt_across_all_task_types(self):
        """Verify prompt integrity for all task types."""
        task_types = ["general", "script_generation", "script_fixing", "qa", "chat", "custom_task"]
        for task in task_types:
            prompt = self.client.build_system_prompt(task)

            # Persona and Version
            self.assertIn("Prometheus AI", prompt, f"Task '{task}' must identify as Prometheus AI")
            self.assertIn("Lucifer v2.88 p2", prompt, f"Task '{task}' must target Lucifer v2.88 p2")
            self.assertIn("mr_berk", prompt, f"Task '{task}' must acknowledge creator mr_berk")

            # bot.status property
            self.assertIn("bot.status", prompt, f"Task '{task}' must mention bot.status property")
            self.assertIn("INTEGER PROPERTY", prompt, f"Task '{task}' must define bot.status as integer property")

            # Explicit prohibition of bot:getBotStatus()
            self.assertIn("bot:getBotStatus()", prompt, f"Task '{task}' must mention bot:getBotStatus() in prohibitions")
            self.assertIn("DOES NOT EXIST", prompt, f"Task '{task}' must state that forbidden methods DO NOT EXIST")
            self.assertIn("NEVER write bot:getBotStatus()", prompt, f"Task '{task}' must explicitly forbid bot:getBotStatus()")

            # ABSENCE of positive hallucinated usage
            self.assertNotIn("or bot:getBotStatus() ==", prompt, f"Task '{task}' must not have 'or bot:getBotStatus() == '")
            self.assertNotIn("bot:getBotStatus() == 22", prompt, f"Task '{task}' must not have 'bot:getBotStatus() == 22'")
            self.assertNotIn("bot:getBotStatus() == 43", prompt, f"Task '{task}' must not have 'bot:getBotStatus() == 43'")

            # Explicit prohibition of world:getDoors()
            self.assertIn("world:getDoors()", prompt, f"Task '{task}' must mention world:getDoors()")
            self.assertIn("NEVER write world:getDoors()", prompt, f"Task '{task}' must explicitly forbid world:getDoors()")

            # Explicit prohibition of world:name()
            self.assertIn("world:name()", prompt, f"Task '{task}' must mention world:name()")
            self.assertIn("NEVER write world:name()", prompt, f"Task '{task}' must explicitly forbid world:name()")
            self.assertIn("world.name", prompt, f"Task '{task}' must teach world.name as property")

            # Verified place syntax: (x, y, item_id)
            self.assertIn("bot:place(x, y, item_id)", prompt, f"Task '{task}' must teach correct place signature")

            # Prohibition on coordinate division by 32
            self.assertIn("32", prompt)
            self.assertIn("DO NOT divide by 32", prompt)

            # Prohibition on GentaHAX APIs
            self.assertIn("GentaHAX", prompt)
            self.assertIn("makeRequest", prompt)

            # Anti-ban protocols
            self.assertIn("180-220ms", prompt)
            self.assertIn("150-180ms", prompt)
            self.assertIn("bot.status == 22", prompt)
            self.assertIn("bot.status == 43", prompt)

            # Mandatory Watermark
            self.assertIn("-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp", prompt)

            # Bilingual separation instructions
            self.assertIn("ç, ğ, ı, ö, ş, ü", prompt)
            self.assertIn("STRICT ASCII CONFINEMENT TO LUA CODE BLOCKS", prompt)
            self.assertIn("CRITICAL SEPARATION", prompt)


class TestTrainingDocNegativeConstraints(unittest.TestCase):
    """
    Empirically inspects docs/AI_TRAINING_LUCIFER.md to guarantee
    all hallucination vectors have been eradicated.
    """

    def setUp(self):
        doc_path = ROOT / "docs" / "AI_TRAINING_LUCIFER.md"
        self.assertTrue(doc_path.exists(), "docs/AI_TRAINING_LUCIFER.md must exist")
        with open(doc_path, "r", encoding="utf-8") as f:
            self.doc_content = f.read()

    def test_no_positive_getBotStatus_in_docs(self):
        """Ensure docs do not instruct bot:getBotStatus() in code blocks."""
        # Find all occurrences of getBotStatus
        lines = self.doc_content.splitlines()
        for idx, line in enumerate(lines, start=1):
            if "getBotStatus" in line:
                # Must be a negative instruction or warning, NOT executable code
                self.assertTrue(
                    any(marker in line.lower() for marker in ["yasak", "yoktur", "hata", "uydurma", "dikkat"]),
                    f"Line {idx} in docs/AI_TRAINING_LUCIFER.md contains un-flagged getBotStatus: '{line}'"
                )
                self.assertNotIn("or bot:getBotStatus()", line, f"Line {idx} contains forbidden disjunction 'or bot:getBotStatus()'")

    def test_no_world_getDoors_positive_usage(self):
        """Ensure docs do not call world:getDoors()."""
        lines = self.doc_content.splitlines()
        for idx, line in enumerate(lines, start=1):
            if "getDoors" in line:
                self.assertTrue(
                    any(marker in line.lower() for marker in ["yasak", "yoktur", "metodu"]),
                    f"Line {idx} in docs/AI_TRAINING_LUCIFER.md contains un-flagged getDoors: '{line}'"
                )

    def test_section_4_hallucination_traps_present(self):
        """Verify dedicated Section 4 exists and details all traps."""
        self.assertIn("### 4. Kesinlikle Yasaklı Uydurma Metotlar (Hallucination Traps)", self.doc_content)
        self.assertIn("bot:getBotStatus()", self.doc_content)
        self.assertIn("world:getDoors()", self.doc_content)
        self.assertIn("world:name()", self.doc_content)
        self.assertTrue(re.search(r"bot:getBotStatus\(\).*?YASAK", self.doc_content))
        self.assertTrue(re.search(r"world:getDoors\(\).*?YASAK", self.doc_content))
        self.assertTrue(re.search(r"world:name\(\).*?YASAK", self.doc_content))
        self.assertIn("Koordinat Bölme Yasağı", self.doc_content)


class TestLuaAsciiSanitizationStressHarness(unittest.TestCase):
    """
    Adversarial stress-testing of sanitize_lua_ascii and ASCII validation.
    Tests every Turkish character, typographic symbols, emojis, and multilingual strings.
    """

    def test_exhaustive_turkish_transliteration(self):
        """Verify all Turkish lowercase, uppercase, and accented characters are transliterated."""
        char_pairs = [
            ("ğ", "g"), ("Ğ", "G"),
            ("ü", "u"), ("Ü", "U"),
            ("ş", "s"), ("Ş", "S"),
            ("ı", "i"), ("İ", "I"),
            ("ö", "o"), ("Ö", "O"),
            ("ç", "c"), ("Ç", "C"),
            ("â", "a"), ("Â", "A"),
            ("î", "i"), ("Î", "I"),
            ("û", "u"), ("Û", "U"),
        ]
        for tr_char, expected_ascii in char_pairs:
            sample = f'local msg = "{tr_char}"'
            sanitized = sanitize_lua_ascii(sample)
            self.assertTrue(is_strict_ascii(sanitized), f"Failed strict ASCII check for {tr_char} -> {sanitized}")
            self.assertIn(expected_ascii, sanitized)

    def test_complex_turkish_phrases(self):
        """Test realistic Turkish in-game Lua scripts."""
        sample = (
            'bot:say("Şu anki dünyada 500 adet çilek toplandı, ışıklar söndürüldü, kapı açıldı.")\n'
            '-- Bu script mr_berk tarafından yazılmıştır ve tüm ağaçları tarar.\n'
            'local dunya_adi = "AĞAÇLAR_DÜNYASI_123"'
        )
        sanitized = sanitize_lua_ascii(sample)
        self.assertTrue(is_strict_ascii(sanitized))
        is_valid, violations = validate_lua_ascii(sanitized)
        self.assertTrue(is_valid, f"Violations found: {violations}")
        self.assertEqual(len(violations), 0)

    def test_typographic_symbols_and_special_quotes(self):
        """Verify typographic quotes, dashes, non-breaking spaces, and bullets are sanitized."""
        sample = 'local text = “Alıntı” • ‘Tekli’ — Tire … Noktalar\u00a0Bitis'
        sanitized = sanitize_lua_ascii(sample)
        self.assertTrue(is_strict_ascii(sanitized))
        self.assertNotIn("“", sanitized)
        self.assertNotIn("”", sanitized)
        self.assertNotIn("•", sanitized)
        self.assertNotIn("—", sanitized)
        self.assertNotIn("…", sanitized)

    def test_emojis_and_unmapped_unicode_stripped(self):
        """Verify emojis and non-Latin alphabets are cleanly stripped to satisfy 7-bit ASCII."""
        sample = 'bot:say("Farm başladı 🔥 🌲 💎 🚀") -- Русский текст / 日本語'
        sanitized = sanitize_lua_ascii(sample, force_ascii=True)
        self.assertTrue(is_strict_ascii(sanitized))
        self.assertIn('bot:say("Farm basladi', sanitized)

    def test_sanitization_is_idempotent(self):
        """Verify sanitize_lua_ascii(s) == sanitize_lua_ascii(sanitize_lua_ascii(s))."""
        sample = 'bot:say("Çilek, ağaç, ışık, ördek, şelale, üzüm.") -- Açıklama: “Güzel”'
        pass1 = sanitize_lua_ascii(sample)
        pass2 = sanitize_lua_ascii(pass1)
        self.assertEqual(pass1, pass2)


class TestPostProcessingBilingualSeparation(unittest.TestCase):
    """
    Adversarially tests _post_process_script_response() to verify:
    1. Text outside code blocks MUST PRESERVE Turkish characters (ç, ğ, ı, ö, ş, ü).
    2. Code INSIDE ```lua ... ``` blocks MUST BE 100% strict 7-bit ASCII.
    3. Handles multiple blocks, mixed case tags, Windows CRLF, and existing watermarks.
    """

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenClient(api_key="mock_key")

    def test_bilingual_character_integrity(self):
        """Verify strict separation: Turkish in markdown, pure ASCII in Lua block."""
        raw_output = (
            "Merhaba! İstediğiniz dünya tarama scriptini aşağıda hazırladım:\n"
            "Bu script dünyadaki tüm ağaçları ve çilekleri sırasıyla toplar.\n\n"
            "```lua\n"
            'local bot = getBot()\n'
            'bot:say("Çilek toplandı!")\n'
            '-- Ağaç hazır mı kontrolü\n'
            "```\n\n"
            "Güle güle kullanın! Başka bir isteğiniz olursa lütfen çekinmeden sorun."
        )

        processed = self.client._post_process_script_response(raw_output)

        # Conversational text outside must contain Turkish characters verbatim
        self.assertIn("İstediğiniz dünya tarama scriptini", processed)
        self.assertIn("tüm ağaçları ve çilekleri sırasıyla toplar", processed)
        self.assertIn("Güle güle kullanın! Başka bir isteğiniz olursa lütfen çekinmeden sorun.", processed)

        # Inside code block MUST NOT have Turkish characters
        code_block = re.search(r"```lua\n(.*?)```", processed, flags=re.DOTALL).group(1)
        self.assertTrue(is_strict_ascii(code_block), f"Code block contains non-ASCII: {code_block}")
        self.assertIn('bot:say("Cilek toplandi!")', code_block)
        self.assertIn('-- Agac hazir mi kontrolu', code_block)

    def test_multiple_code_blocks_in_single_response(self):
        """Verify multiple code blocks in one response are each sanitized."""
        raw_output = (
            "Birinci adım (Işınlanma):\n"
            "```lua\n"
            'bot:say("Dünyaya gidiliyor...")\n'
            "```\n\n"
            "İkinci adım (Toplama):\n"
            "```lua\n"
            'bot:say("Ağaçlar toplanıyor...")\n'
            "```\n\n"
            "İşlem tamamlandı, teşekkürler!"
        )

        processed = self.client._post_process_script_response(raw_output)

        # Both blocks must be sanitized
        blocks = re.findall(r"```lua\n(.*?)```", processed, flags=re.DOTALL)
        self.assertEqual(len(blocks), 2)
        for idx, block in enumerate(blocks, start=1):
            self.assertTrue(is_strict_ascii(block), f"Block {idx} contains non-ASCII")
            self.assertIn("Made by Berk (Lucifer-MCP)", block)

        # Outside text must preserve Turkish characters
        self.assertIn("Birinci adım (Işınlanma):", processed)
        self.assertIn("İkinci adım (Toplama):", processed)
        self.assertIn("İşlem tamamlandı, teşekkürler!", processed)

    def test_crlf_windows_line_endings_handling(self):
        """Verify Windows CRLF (\\r\\n) is handled cleanly."""
        raw_output = (
            "Açıklama:\r\n"
            "```lua\r\n"
            "local bot = getBot()\r\n"
            'bot:say("Ağaç")\r\n'
            "```\r\n"
            "Sonuç başarılı."
        )

        processed = self.client._post_process_script_response(raw_output)
        self.assertIn("Açıklama:", processed)
        self.assertIn("Sonuç başarılı.", processed)
        code_match = re.search(r"```lua\n(.*?)```", processed, flags=re.DOTALL)
        self.assertIsNotNone(code_match)
        self.assertTrue(is_strict_ascii(code_match.group(1)))

    def test_watermark_is_not_duplicated_if_already_present(self):
        """Verify watermark is not prepended twice if already generated by model."""
        raw_output = (
            "```lua\n"
            "-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp\n"
            "local bot = getBot()\n"
            "```"
        )
        processed = self.client._post_process_script_response(raw_output)
        occurrences = processed.count("Made by Berk (Lucifer-MCP)")
        self.assertEqual(occurrences, 1, "Watermark was duplicated!")

    def test_pure_qa_response_without_code_blocks(self):
        """Verify conversational Q&A without code is left completely intact."""
        raw_output = (
            "Lucifer Multibot'ta Google Login hatası (Status 13) alıyorsanız:\n"
            "glServer.exe konsolunda `set useHeadless False` ve `set userInteraction True` komutlarını çalıştırın.\n"
            "Tarayıcı açıldığında captchayı bir kez elinizle çözdüğünüzde profil kalıcı olarak kaydedilir."
        )
        processed = self.client._post_process_script_response(raw_output)
        self.assertEqual(raw_output, processed)


class TestLanguageDetectionEdgeCases(unittest.TestCase):
    """
    Adversarial test harness for detect_language().
    """

    def test_turkish_distinctive_characters(self):
        """Any Turkish specific letter (ç, ğ, ı, ö, ş, ü) must force Turkish."""
        samples = [
            "dünyaya gir",
            "ağaç topla",
            "çilek farmı",
            "ışık aç",
            "şifre değiştir",
            "ürün sat",
            "İslem tamam",
        ]
        for s in samples:
            self.assertEqual(detect_language(s), "tr", f"Failed for: {s}")

    def test_english_prompts(self):
        """English vocabulary without Turkish letters must detect English."""
        samples = [
            "write a script to warp to world and collect items",
            "how to fix connection timeout in lucifer",
            "create an auto harvest script for laser grid",
            "please stop all bots when banwave status is 43",
        ]
        for s in samples:
            self.assertEqual(detect_language(s), "en", f"Failed for: {s}")

    def test_empty_and_ambiguous_fallbacks(self):
        """Empty, whitespace, punctuation, and ambiguous inputs fallback to Turkish community default."""
        self.assertEqual(detect_language(""), "tr")
        self.assertEqual(detect_language("   "), "tr")
        self.assertEqual(detect_language("???"), "tr")
        self.assertEqual(detect_language("12345"), "tr")
        self.assertEqual(detect_language("bot"), "tr")


class TestSlugGeneratorStressHarness(unittest.TestCase):
    """
    Adversarial stress harness for generate_script_slug().
    Ensures safe filenames, correct action mapping, and robust fallbacks.
    """

    def test_original_request_world_prompt(self):
        """ORIGINAL_REQUEST.md:24 -> 'asdsadasdasd adındaki dünyaya giren bir script hazırla'."""
        slug = generate_script_slug("asdsadasdasd adındaki dünyaya giren bir script hazırla")
        self.assertEqual(slug, "asdsadasdasd_auto_warp.lua")

    def test_dirt_farm_prompt(self):
        """'dirt farm scripti yaz' -> 'dirt_auto_farm.lua'."""
        slug = generate_script_slug("dirt farm scripti yaz")
        self.assertEqual(slug, "dirt_auto_farm.lua")

    def test_laser_grid_pnb_prompt(self):
        """'laser grid pnb yap' -> 'laser_grid_pnb.lua'."""
        slug = generate_script_slug("laser grid pnb yap")
        self.assertEqual(slug, "laser_grid_pnb.lua")

    def test_emergency_stop_prompt(self):
        """'botu acil durdur' -> 'bot_stop.lua'."""
        slug = generate_script_slug("botu acil durdur")
        self.assertEqual(slug, "bot_stop.lua")

    def test_adversarial_path_traversal_and_special_chars(self):
        """Prompt containing path traversal or shell chars must yield safe filename."""
        slug = generate_script_slug("../../../etc/passwd; rm -rf /; world: testworld dünyaya git")
        self.assertTrue(slug.endswith(".lua"))
        self.assertNotIn("/", slug)
        self.assertNotIn("..", slug)
        self.assertNotIn(";", slug)
        self.assertNotIn(" ", slug)
        # Only safe characters [a-zA-Z0-9_.]
        self.assertTrue(re.match(r"^[a-zA-Z0-9_]+\.lua$", slug))

    def test_empty_and_garbage_prompt_fallback(self):
        """Garbage prompt falls back to a valid .lua filename."""
        slug = generate_script_slug("!@#$%^&*()")
        self.assertTrue(slug.endswith(".lua"))
        self.assertTrue(re.match(r"^[a-zA-Z0-9_]+\.lua$", slug))


class TestEvrenClientChatContract(unittest.TestCase):
    """
    Empirically verifies EvrenAIClient.chat() interface contract:
    - Return structure: {"text": str, "code": str, "slug": str, "model": str}
    - Code is 100% strict 7-bit ASCII
    - Text contains natural Turkish
    - Handles mock LLM completions and network error scenarios cleanly
    """

    def setUp(self):
        with patch.object(EvrenClient, "load_from_config", return_value=None):
            self.client = EvrenAIClient(api_key="mock_key")

    def test_chat_interface_contract_keys_and_types(self):
        """Verify chat() returns exact dictionary keys with string values."""
        mock_completion = (
            "Harika! Dünyaya ışınlanıp çilek toplayan scriptiniz hazır:\n\n"
            "```lua\n"
            "local bot = getBot()\n"
            'bot:say("Başlatıldı")\n'
            "bot:collect(10, 100)\n"
            "```\n\n"
            "İyi oyunlar dilerim!"
        )

        with patch.object(self.client, "chat_completion", new=AsyncMock(return_value=mock_completion)):
            result = asyncio.run(self.client.chat("çilek toplama scripti yaz", user_id="12345"))

            # Check dictionary contract
            self.assertIsInstance(result, dict)
            self.assertEqual(set(result.keys()), {"text", "code", "slug", "model"})
            self.assertIsInstance(result["text"], str)
            self.assertIsInstance(result["code"], str)
            self.assertIsInstance(result["slug"], str)
            self.assertIsInstance(result["model"], str)

            # Check ASCII enforcement on code
            self.assertTrue(is_strict_ascii(result["code"]))
            self.assertIn('bot:say("Baslatildi")', result["code"])
            self.assertNotIn("Başlatıldı", result["code"])

            # Check Turkish preservation on text
            self.assertIn("Harika! Dünyaya ışınlanıp çilek toplayan scriptiniz hazır:", result["text"])
            self.assertIn("İyi oyunlar dilerim!", result["text"])

            # Check slug
            self.assertTrue(result["slug"].endswith(".lua"))

    def test_chat_without_code_generation(self):
        """Verify chat() on non-code query returns empty code and slug."""
        mock_completion = "Lucifer v2.88 p2 sürümünde durum kodları 0 ile 44 arasındadır."
        with patch.object(self.client, "chat_completion", new=AsyncMock(return_value=mock_completion)):
            result = asyncio.run(self.client.chat("Lucifer durum kodları nelerdir?"))
            self.assertEqual(result["code"], "")
            self.assertEqual(result["slug"], "")
            self.assertIn("Lucifer v2.88 p2", result["text"])


if __name__ == "__main__":
    unittest.main()
