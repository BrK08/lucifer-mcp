"""
Lucifer Multibot — TÜBİTAK/SSB EVREN AI Platform Client
Connects the Lucifer Discord Community Helper Bot to EVREN LLM Inference API (SSYZ / SAYZEK).
Enforces zero-hallucination Lucifer v2.88 p2 runtime API knowledge, pure ASCII Lua output,
and automatic terms acceptance.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from typing import Any, Dict, List, Optional
import aiohttp

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
DOCS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "AI_TRAINING_LUCIFER.md")


def sanitize_lua_ascii(code: str, force_ascii: bool = True) -> str:
    """
    Replaces non-ASCII Turkish characters and typographic symbols with ASCII counterparts in Lua code.
    Growtopia's in-game font does NOT support Turkish characters and will corrupt or crash.
    When force_ascii is True, guarantees 100% strict 7-bit ASCII (ord < 128) by normalizing
    and stripping any remaining non-ASCII glyphs.
    """
    replacements = {
        # Turkish lower & upper
        "ğ": "g", "Ğ": "G",
        "ü": "u", "Ü": "U",
        "ş": "s", "Ş": "S",
        "ı": "i", "İ": "I",
        "ö": "o", "Ö": "O",
        "ç": "c", "Ç": "C",
        # Circumflex accents
        "â": "a", "Â": "A",
        "î": "i", "Î": "I",
        "û": "u", "Û": "U",
        # Typographic quotes and apostrophes
        "’": "'", "‘": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "«": '"', "»": '"',
        # Typographic dashes and punctuation
        "•": "-", "…": "...",
        "–": "-", "—": "--", "−": "-",
        # Non-standard spaces
        "\u00a0": " ",  # Non-breaking space
        "\u200b": "",   # Zero-width space
        "\u202f": " ",  # Narrow no-break space
    }
    for tr, asc in replacements.items():
        code = code.replace(tr, asc)

    if force_ascii and not all(ord(c) < 128 for c in code):
        decomposed = unicodedata.normalize("NFKD", code)
        ascii_chars = []
        for c in decomposed:
            if ord(c) < 128:
                ascii_chars.append(c)
            elif unicodedata.category(c).startswith("M"):
                continue
            else:
                ascii_chars.append("")
        code = "".join(ascii_chars)

    return code


def _deduplicate_repetitive_paragraphs(text: str) -> str:
    """
    Removes duplicate or near-duplicate (>80% token overlap) paragraphs and headings
    outside ```lua ... ``` code blocks so AI replies stay concise.
    """
    if not text or not isinstance(text, str):
        return text or ""

    segments = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    seen_norms: set[str] = set()
    seen_token_sets: List[set[str]] = []
    seen_sentences: set[str] = set()
    out_segments: List[str] = []
    any_dropped = False

    for seg in segments:
        if seg.startswith("```") and seg.endswith("```"):
            out_segments.append(seg)
            continue

        paragraphs = re.split(r"\n{2,}", seg)
        kept_paragraphs: List[str] = []
        for para in paragraphs:
            stripped = para.strip()
            if not stripped:
                continue
            if stripped == "---":
                if kept_paragraphs and kept_paragraphs[-1] == "---":
                    any_dropped = True
                    continue
                kept_paragraphs.append(stripped)
                continue

            norm = re.sub(r"[^a-z0-9çğıöşü]+", " ", stripped.lower()).strip()
            if not norm:
                continue

            if len(norm) >= 18 and norm in seen_norms:
                any_dropped = True
                continue

            toks = {w for w in norm.split() if len(w) >= 3}
            is_near_dup = False
            if len(toks) >= 6:
                for prev in seen_token_sets:
                    if len(prev) >= 6:
                        overlap = len(toks & prev) / max(1, len(toks))
                        rev_overlap = len(toks & prev) / max(1, len(prev))
                        if overlap > 0.80 and rev_overlap > 0.65:
                            is_near_dup = True
                            break
            if is_near_dup:
                any_dropped = True
                continue

            # Filter exact duplicate long sentences within a paragraph while keeping line breaks intact
            sentences = re.split(r"(?<=[.!?])[ \t]+", stripped)
            if len(sentences) > 1:
                unique_sentences: List[str] = []
                sent_dropped = False
                for sent in sentences:
                    s_norm = re.sub(r"[^a-z0-9çğıöşü]+", " ", sent.lower()).strip()
                    if len(s_norm) >= 24 and s_norm in seen_sentences:
                        sent_dropped = True
                        continue
                    if len(s_norm) >= 24:
                        seen_sentences.add(s_norm)
                    unique_sentences.append(sent)
                if not unique_sentences:
                    any_dropped = True
                    continue
                if sent_dropped:
                    any_dropped = True
                    stripped = " ".join(unique_sentences)
                    norm = re.sub(r"[^a-z0-9çğıöşü]+", " ", stripped.lower()).strip()
                    toks = {w for w in norm.split() if len(w) >= 3}
            else:
                if len(norm) >= 24:
                    seen_sentences.add(norm)

            if len(norm) >= 18:
                seen_norms.add(norm)
            if len(toks) >= 6:
                seen_token_sets.append(toks)
            kept_paragraphs.append(stripped)

        if kept_paragraphs:
            out_segments.append("\n\n".join(kept_paragraphs))

    if not any_dropped:
        return text

    joined = "\n\n".join(s.strip() for s in out_segments if s and s.strip())
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def is_strict_ascii(text: str) -> bool:
    """Returns True if all characters in the string are strict 7-bit ASCII (0-127)."""
    return all(ord(c) < 128 for c in text)


def validate_lua_ascii(text: str) -> tuple[bool, list[dict]]:
    """
    Validates Lua code for ASCII compatibility.
    Returns (is_valid, list_of_violations_with_line_col_info).
    """
    violations = []
    lines = text.splitlines()
    for line_idx, line in enumerate(lines, start=1):
        for col_idx, char in enumerate(line, start=1):
            if ord(char) >= 128:
                violations.append({
                    "line": line_idx,
                    "col": col_idx,
                    "char": char,
                    "codepoint": f"U+{ord(char):04X}",
                    "line_preview": line.strip()[:80],
                })
    return (len(violations) == 0, violations)


def detect_language(text: Any) -> str:
    """
    Detects whether the given user prompt is Turkish ('tr') or English ('en').
    Prioritizes Turkish distinctive characters and common Turkish keywords.
    Defaults to 'tr' if ambiguous for the Lucifer Discord community.
    """
    if text is None:
        return "tr"
    if not isinstance(text, str):
        text = str(text)
    if not text.strip():
        return "tr"

    # Turkish unique letters immediately identify Turkish text
    tr_chars = set("çğıöşüÇĞİÖŞÜ")
    if any(c in tr_chars for c in text):
        return "tr"

    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    tr_keywords = {
        "ve", "bir", "bu", "icin", "ile", "da", "de", "ne", "kadar", "nasil",
        "yap", "yaz", "topla", "bot", "dunya", "koy", "al", "baslat", "calis",
        "calisiyor", "hata", "kod", "scripti", "yardim", "neden", "bana", "ben",
        "sen", "mi", "mu", "lutfen", "onarma", "tamir", "bak", "dur"
    }
    en_keywords = {
        "the", "and", "is", "in", "to", "for", "with", "write", "make", "create",
        "harvest", "collect", "warp", "enter", "world", "how", "what", "why",
        "please", "fix", "error", "when", "from", "generate", "farm", "code",
        "door", "start", "stop", "status", "bot", "connect", "bridge", "setup",
        "guide", "help", "tutorial"
    }

    tr_score = len(words.intersection(tr_keywords))
    en_score = len(words.intersection(en_keywords))

    if en_score > tr_score:
        return "en"
    return "tr"


ITEM_KEYWORDS = {
    "dirt": "dirt",
    "sugar cane": "sugar_cane",
    "sugarcane": "sugar_cane",
    "laser grid": "laser_grid",
    "lasergrid": "laser_grid",
    "lgrid": "laser_grid",
    "pepper": "pepper",
    "chandelier": "chandelier",
    "chnd": "chandelier",
    "seed": "seed",
    "fish": "fish",
    "geiger": "geiger",
}

ACTION_KEYWORDS = [
    (r"(?:isinlan|ışınlan|warp|gir|enter|go to)", "auto_warp"),
    (r"(?:farm|ek|dik|hasat|harvest|plant|tohum)", "auto_farm"),
    (r"(?:pnb|break|kir|kır)", "pnb"),
    (r"(?:topla|collect|cek|çek)", "auto_collect"),
    (r"(?:balik|balık|fish)", "auto_fish"),
    (r"(?:geiger)", "auto_geiger"),
    (r"(?:depo|store|drop|sakla)", "auto_store"),
    (r"(?:durdur|stop|halt)", "bot_stop"),
]


def generate_script_slug(prompt: str, item_hint: str = "", code: str = "") -> str:
    """
    Generates a descriptive, semantic Lua script filename slug based on prompt, item_hint, and code.
    Example: 'asdsadasdasd adındaki dünyaya giren bir script hazırla' -> 'asdsadasdasd_auto_warp.lua'
    Example: 'dirt farm scripti yaz' -> 'dirt_auto_farm.lua'
    """
    if not prompt or not str(prompt).strip():
        return "lucifer_script.lua"

    # If 2nd parameter looks like code rather than item hint, swap
    if item_hint and ("\n" in item_hint or "getBot" in item_hint or "--" in item_hint):
        code = item_hint
        item_hint = ""

    p_lower = (prompt or "").lower()

    # 1. World name extraction (e.g. "asdsadasdasd adındaki dünyaya")
    world_match = re.search(
        r'\b([a-zA-Z0-9]{3,24})\s+(?:adındaki|adli|adlı|isimli|adında|world|dünyas?ı?n?a?|dunyasına)\b',
        p_lower,
    )
    world_name = world_match.group(1).lower() if world_match else ""
    if world_name in ("bir", "olan", "icin", "için", "olan", "yeni", "script", "lua", "bot"):
        world_name = ""

    # 2. Item extraction
    detected_item = ""
    if item_hint:
        detected_item = re.sub(
            r'[^a-zA-Z0-9_]', '', item_hint.split('(')[0].strip().lower().replace(" ", "_")
        )
    if not detected_item:
        for k, v in ITEM_KEYWORDS.items():
            if k in p_lower:
                detected_item = v
                break

    # 3. Action extraction
    detected_action = ""
    extended_actions = ACTION_KEYWORDS + [
        (r"(?:baglan|bağlan|test|kontrol|check|status|ping|durum|connect)", "connection_test")
    ]
    for pattern, act in extended_actions:
        if re.search(pattern, p_lower):
            detected_action = act
            break

    components = []
    if world_name:
        components.append(world_name)
    if detected_item and detected_item not in components:
        components.append(detected_item)
    if detected_action:
        components.append(detected_action)
    elif not components:
        components.append("bot_automation")

    slug = "_".join(components)
    slug = re.sub(r'[^a-zA-Z0-9_]', '', slug).strip('_')
    if not slug:
        slug = "bot_automation"

    return f"{slug}.lua"



class EvrenClient:
    """Client for TÜBİTAK/SSB EVREN Yapay Zekâ Platformu (SSYZ) LLM API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        project_id: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._explicit_api_key = api_key is not None
        self._explicit_base_url = base_url is not None
        self._explicit_project_id = project_id is not None
        self._explicit_model = model is not None

        self.api_key = api_key if self._explicit_api_key else os.getenv("EVREN_API_KEY", "")
        default_base_url = "https://evren-llmapi.ssyz.org.tr/v1"
        self.base_url = (base_url or os.getenv("EVREN_BASE_URL", default_base_url)).rstrip("/")
        default_project_id = "01a1c1b0-4d25-7ea0-b8c8-3f26c81c662b"
        self.project_id = project_id or os.getenv("EVREN_PROJECT_ID", default_project_id)
        self.model = model or os.getenv("EVREN_MODEL", "auto")
        self.custom_system_prompt: Optional[str] = None
        self._terms_accepted = False
        self._knowledge_base = ""
        self.load_from_config()
        self.load_knowledge_base()

    def load_from_config(self):
        """Loads EVREN AI configuration from config.json if available without overwriting explicit params."""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    evren_cfg = cfg.get("ai")
                    if not isinstance(evren_cfg, dict):
                        evren_cfg = cfg.get("evren_ai", {})
                    if not isinstance(evren_cfg, dict):
                        evren_cfg = {}

                    if not self._explicit_api_key and evren_cfg.get("api_key") and not self.api_key:
                        self.api_key = evren_cfg["api_key"]
                    if not self._explicit_base_url and evren_cfg.get("base_url"):
                        self.base_url = evren_cfg["base_url"].rstrip("/")
                    if not self._explicit_project_id and evren_cfg.get("project_id"):
                        self.project_id = evren_cfg["project_id"]
                    if not self._explicit_model and evren_cfg.get("model"):
                        self.model = evren_cfg["model"]
            except Exception as e:
                print(f"[EvrenClient] Failed to load config: {e}")

    def load_knowledge_base(self):
        """Loads and extracts core knowledge from docs/AI_TRAINING_LUCIFER.md."""
        if os.path.exists(DOCS_PATH):
            try:
                with open(DOCS_PATH, "r", encoding="utf-8") as f:
                    self._knowledge_base = f.read()
            except Exception as e:
                print(f"[EvrenClient] Failed to read knowledge base file: {e}")

    @property
    def is_configured(self) -> bool:
        """Returns True if a real API key is set."""
        return bool(
            self.api_key
            and "YOUR_EVREN_API_KEY" not in self.api_key
            and "YOUR_AI_API_KEY" not in self.api_key
        )

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
        }
        if self.project_id:
            headers["X-Project-ID"] = self.project_id
        return headers

    async def ensure_terms_accepted(self) -> bool:
        """
        EVREN LLM API requires accepting terms of use before chat completion works.
        Calls GET /v1/terms/status and POST /v1/terms/accept if needed.
        """
        if self._terms_accepted or not self.is_configured:
            return True

        url_status = f"{self.base_url}/terms/status"
        url_accept = f"{self.base_url}/terms/accept"
        headers = self._get_headers()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_status, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("accepted") or data.get("is_accepted"):
                            self._terms_accepted = True
                            return True
                        current_ver = data.get("current_version") or data.get("version") or "1.0"
                        async with session.post(
                            url_accept, headers=headers, json={"version": current_ver}, timeout=aiohttp.ClientTimeout(total=5)
                        ) as acc_resp:
                            if acc_resp.status in (200, 201):
                                self._terms_accepted = True
                                return True
        except Exception as e:
            print(f"[EvrenClient] Terms check note: {e}")
            # Do not block execution, might already be accepted
        return True

    def build_system_prompt(self, task_type: str = "general") -> str:
        """Builds an authoritative, zero-hallucination system prompt for EVREN LLM."""
        if self.custom_system_prompt:
            return self.custom_system_prompt

        return (
            "You are Prometheus AI, the Official AI Assistant & Script Engine for the Lucifer Multibot (Growtopia) Community.\n"
            "You were created by mr_berk. specifically for Lucifer v2.88 p2.\n\n"
            "LANGUAGE & CHARACTER PROTOCOL (MANDATORY):\n"
            "1. BILINGUAL ADAPTATION:\n"
            "   - Turkish Queries: When the user speaks or writes in Turkish, you MUST respond in fluent, natural, grammatically correct Turkish.\n"
            "     YOU MUST USE PROPER TURKISH CHARACTERS (ç, ğ, ı, ö, ş, ü, Ç, Ğ, İ, Ö, Ş, Ü) in all your explanations, markdown formatting, warnings, and conversational text!\n"
            "     NEVER strip Turkish characters or use ASCII transliteration in your normal conversational writing!\n"
            "   - English Queries: When the user speaks or writes in English, you MUST respond in fluent, natural, grammatically correct English.\n"
            "   - Match the user's input language automatically unless requested otherwise.\n"
            "2. STRICT ASCII CONFINEMENT TO LUA CODE BLOCKS:\n"
            "   - Growtopia's in-game bitmap font only supports 7-bit ASCII characters (codepoints 32 to 126). Non-ASCII characters corrupt the font or trigger packet disconnects.\n"
            "   - INSIDE ```lua ... ``` CODE BLOCKS (and attached .lua files):\n"
            "     * All Lua code, string literals (such as bot:say('...'), print('...')), comments, variable names, and table keys MUST BE 100% STRICT ASCII ONLY.\n"
            "     * In Lua strings and comments, always transliterate Turkish characters: (ç->c, ğ->g, ı->i, ö->o, ş->s, ü->u, etc.). E.g. 'Agac buyudu', 'Baslatildi', 'Cikis'.\n"
            "   - CRITICAL SEPARATION: The ASCII restriction applies ONLY to the code inside ```lua ... ``` blocks. Your natural language explanations, markdown text, and chat outside the code block MUST use proper Turkish characters when writing in Turkish!\n\n"
            "CRITICAL LUCIFER RUNTIME RULES:\n"
            "1. TARGET CLIENT IS LUCIFER v2.88 p2 ONLY: DO NOT EVER use GentaHAX APIs (e.g. makeRequest, requestTileChange, checkTile, AddHook, ImGui, runThread). They will immediately crash or fail in Lucifer.\n"
            "2. VERIFIED LUCIFER C++ RUNTIME API:\n"
            "   - Single bot: bot = getBot()\n"
            "   - All bots: bots = getBots()\n"
            "   - Bot status: bot.status is an INTEGER PROPERTY (0-44). CRITICAL: bot:getBotStatus() DOES NOT EXIST and will crash the script with a nil error. NEVER use bot:getBotStatus(). ALWAYS check bot.status (e.g. if bot.status == 22 then).\n"
            "   - Movement: bot:findPath(x, y) (Note: bot.x and bot.y are ALREADY tile coordinates, DO NOT divide by 32!)\n"
            "   - Actions: bot:place(x, y, item_id), bot:hit(x, y) or bot:punch(x, y), bot:collect(range, interval), bot:warp(world, door_id), bot:say(text)\n"
            "   - World access: world = bot:getWorld(), tile = world:getTile(x, y), tile_list = world:getTiles(), players = world:getPlayers(), objects = world:getObjects()\n"
            "   - World properties: world.name is a STRING PROPERTY (use world.name == 'TARGET', NEVER call world:name()).\n"
            "   - Doors & Warping: world:getDoors() DOES NOT EXIST in Lucifer. Warping to a target door is done via bot:warp(world_name, door_id) or bot:warp(world_name). To scan doors, iterate world:getTiles() and check tile.fg == 6 (door) or tile.fg == 12 (main door).\n"
            "   - Tile attributes: tile.fg, tile.bg, tile.x, tile.y, tile.flags, tile:canHarvest(), tile:hasExtra(), tile:getExtra()\n"
            "   - TileExtra: extra.id, extra.growth (seconds elapsed since planted), extra.count, extra.flags\n"
            "   - Seed growth total: getInfo(seed_id).growth (seconds required to fully grow)\n"
            "   - Inventory: inv = bot:getInventory():getItems() -> for _, it in pairs(inv) do it.id, it.count, it.isActive end (or bot:getInventory():getItemCount(item_id)). Actions: bot:drop(item_id, count), bot:trash(item_id, count), bot:wear(item_id), bot:unwear(item_id), bot:use(item_id). Item IDs: Dirt=2, Dirt Seed=3, Lava=4, Rock=10, Cave Dirt=14, World Lock=242, Diamond Lock=1796, Blue Gem Lock=7188, Pepper Tree=4584.\n"
            "   - HTTP Requests in Lucifer: Use HttpClient.new() (client.url = '...', client.headers = { ['Content-Type'] = 'application/json' }, client.method = Method.post, client:request()). CRITICAL: makeRequest() DOES NOT EXIST in Lucifer.\n"
            "   - Connection & Automations (Lucifer v2.88 p2): bot.auto_reconnect = true/false, bot:connect(), bot:disconnect(), bot.auto_farm.enabled = true/false, bot.rotation.enabled = true/false, bot.auto_geiger.enabled = true/false, bot.auto_spam.enabled = true/false, bot.auto_fish.enabled = true/false, bot.auto_cook.enabled = true/false, bot.auto_transfer.enabled = true/false, bot.auto_harvest.enabled = true/false, bot.auto_plant.enabled = true/false, bot.auto_collect = true/false, bot.auto_trash = true/false.\n"
            "3. STRICT HALLUCINATION BANS & FORBIDDEN METHODS (CRITICAL):\n"
            "   - NEVER write bot:login(\"username\", \"password\")! It DOES NOT EXIST. Use bot:connect(), bot:disconnect(), or bot.auto_reconnect = true.\n"
            "   - NEVER write bot:getBotStatus()! This method DOES NOT EXIST and crashes the script with a nil error. ALWAYS check bot.status (e.g. if bot.status == 22 then).\n"
            "   - NEVER write world:getDoors()! This method DOES NOT EXIST. To warp, call bot:warp(targetWorld, door_id). To scan doors in the current world, iterate world:getTiles() checking tile.fg == 6 (door) or tile.fg == 12 (main door).\n"
            "   - NEVER write world:name()! world.name is a property, NOT a method.\n"
            "   - NEVER invent nonexistent methods on bot, world, tile, or inventory. Stick 100% to verified Lucifer APIs.\n"
            "   - NEVER divide bot.x or bot.y by 32.\n"
            "4. ANTI-BAN & STEALTH PROTOCOLS (MANDATORY TO AVOID UBISOFT BANS):\n"
            "   - Humanized Jitter Delays: NEVER use static sleep values! Always use randomized jitter: e.g. sleep(170 + math.random(15, 45)).\n"
            "   - Minimum Safe Delays: Punch/Hit: 180-220ms, Place: 150-180ms, Warp: 3500-5000ms, Drop/Trash: 300-500ms.\n"
            "   - Moderator Auto-Evasion: In every automation loop, check for mods: if bot.status == 22 then bot:warp('EXIT') sleep(4000) return end.\n"
            "   - Banwave Safety: If banwave is detected (bot.status == 43), halt actions: if bot.status == 43 then sleep(60000) return end.\n"
            "   - No Teleport/Noclip: Always navigate using bot:findPath(x, y), never teleport directly through solid tiles.\n"
            "5. ZERO LOGIC ERRORS & STABILITY PROTOCOLS:\n"
            "   - World & Tile Nil Checks: ALWAYS check if world and tile exist before indexing (if not world then sleep(1000) return end).\n"
            "   - Inventory Validation: NEVER call bot:place() if the item count is 0 in inventory! Check item count first.\n"
            "   - Tree Harvest Check: ALWAYS check if tile:canHarvest() is true before hitting a tree! Do not punch unready saplings.\n"
            "   - Inventory Full Check: Before harvesting or collecting, check if inventory has space (count < 200). If full, drop/store first.\n"
            "   - Never Infinite-Loop Without Delay: EVERY while loop MUST contain sleep(ms) inside to prevent freezing the Lua engine.\n"
            "   - Coordinate Bounds: Always ensure 0 <= x < 100 and 0 <= y < 60. DO NOT divide by 32!\n"
            "6. WATERMARK MANDATORY: Every generated Lua script MUST start with:\n"
            "   -- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp\n"
            "7. GLSERVER CAPTCHA SOLVING KNOWLEDGE: When asked about Google Login captcha (Status 13 - Couldn't Solve Captcha), "
            "the permanent solution is: In glServer.exe console, run: set useHeadless False, set userInteraction True, set saveProfile True. "
            "Log in once with visible browser, solve captcha manually, and the session profile is permanently saved in chrome/ folder.\n"
            "8. CONSEQUENCE-AWARE STRATEGIC ADVISORY & USER CONFIRMATION (MANDATORY):\n"
            "   - Multi-Account Single-IP Hazard: When a user gives account credentials or asks to connect multiple accounts (>2 bots) without proxies, "
            "DO NOT execute blindly! ALWAYS warn first: Connecting >2 bots on a single home IP triggers Ubisoft's http_block (Status 13) or permanent location_banned (Status 5). "
            "Advise setting proxies in Lucifer ProxyManager, and explicitly ask for confirmation before proceeding with multiple bots on one IP.\n"
            "   - Login Method Intelligence: Always determine the correct login method for given credentials:\n"
            "     * If email ends with @gmail.com -> MUST use glServer.exe (Gmaillog Settings -> accessKey) via Google OAuth.\n"
            "     * If username has no @ -> Use legacy direct GrowID + Password auth.\n"
            "   - Mass Warp Staggering: When sending 3+ bots to the same world simultaneously, advise 4-7 second staggered intervals to avoid triggering world anti-raid alarms.\n"
            "   - Asset Safety: When writing scripts that drop/store valuable items (WLs, DLs, BGLs), always check world:hasAccess() first to prevent theft in public worlds.\n"
            "   - Speed Limits: Refuse or strongly warn against action delays below 160ms (autoban speed threshold).\n"
            "9. Keep responses clear, helpful, and developer-friendly. Always explain why a fix, warning, or method is used.\n"
            "10. ANTI-REPETITION & NO UNSOLICITED LUA SCRIPTS (MANDATORY):\n"
            "   - NEVER repeat the same explanation, seed list, or advice under multiple headings. Answer concisely in a single pass.\n"
            "   - When the user asks a Growtopia recipe/mass/inventory question (not asking to write a Lua script), NEVER output a ```lua block telling them how to check their inventory — use the provided Live Connected Bot Telemetry and Verified Growtopia Recipe Data directly."
        )

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Executes a chat completion request to the AI LLM API."""
        if not self.is_configured:
            return (
                "⚠️ **AI API Anahtarı Tanımlanmamış!**\n\n"
                "1. `config.json` dosyasında `evren_ai.api_key` alanına API anahtarınızı girin.\n"
                "2. Veya Discord üzerinden `/ai_set_key` komutuyla anahtarınızı tanımlayın."
            )

        await self.ensure_terms_accepted()

        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content", "")
                            return content.strip()
                        return "⚠️ AI yanıt döndürdü fakat içerik boştu."
                    elif resp.status == 401:
                        return "❌ **AI Yetkilendirme Hatası (401):** API anahtarı geçersiz veya süresi dolmuş."
                    elif resp.status == 429:
                        return "⏳ **AI Kota Limiti (429):** Günlük token veya istek kotası aşıldı. Lütfen biraz sonra tekrar deneyin."
                    else:
                        text = await resp.text()
                        return f"❌ **AI API Hatası ({resp.status}):** {text[:300]}"
        except asyncio.TimeoutError:
            return "⏱️ **Zaman Aşımı:** AI sunucusu 45 saniye içinde yanıt veremedi. Lütfen tekrar deneyin."
        except Exception as e:
            return f"❌ **Bağlantı Hatası:** AI API'sine erişilemedi: {str(e)}"

    async def generate_script(self, prompt: str, item_hint: str = "", delay_ms: int = 200) -> str:
        """Generates a complete Lucifer v2.88 p2 Lua automation script."""
        system_prompt = self.build_system_prompt("script_generation")
        user_message = (
            f"Write a complete, robust, ready-to-execute Lucifer v2.88 p2 Lua script for the following request:\n"
            f"Prompt: {prompt}\n"
        )
        if item_hint:
            user_message += f"Target Item / ID: {item_hint}\n"
        user_message += (
            f"Action Delay: {delay_ms}ms\n\n"
            f"IMPORTANT REQUIREMENTS:\n"
            f"- Output ONLY pure ASCII characters in Lua strings (NO Turkish characters like ğ, ü, ş, ı, ö, ç).\n"
            f"- Add header: -- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp\n"
            f"- Wrap the code in a ```lua ... ``` markdown block.\n"
            f"- Add concise explanations below the code block."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        raw_response = await self.chat_completion(messages, temperature=0.2, max_tokens=2500)
        # Extract Lua blocks and sanitize to ensure 100% pure ASCII in code
        return self._post_process_script_response(raw_response)

    async def fix_script(self, code_or_error: str, error_context: str = "") -> str:
        """Analyzes and fixes a broken script or diagnoses an error message."""
        system_prompt = self.build_system_prompt("script_fixing")
        user_message = (
            f"A Lucifer Multibot user provided the following broken script and/or error message:\n\n"
            f"```lua\n{code_or_error}\n```\n"
        )
        if error_context:
            user_message += f"\nError Context: {error_context}\n"

        user_message += (
            "\nPlease:\n"
            "1. Diagnose the exact bug (e.g. GentaHAX API hallucination like makeRequest/requestTileChange, "
            "missing delays, dividing tile coordinates by 32, Turkish characters in strings, threading issues).\n"
            "2. Provide the 100% working, fixed Lucifer v2.88 p2 script in a ```lua ... ``` block.\n"
            "3. Enforce pure ASCII in Lua strings and include header: -- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp.\n"
            "4. Explain the fix concisely."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        raw_response = await self.chat_completion(messages, temperature=0.2, max_tokens=2500)
        return self._post_process_script_response(raw_response)

    async def answer_question(self, question: str) -> str:
        """Answers general Lucifer multibot, networking, or scripting questions."""
        system_prompt = self.build_system_prompt("qa")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
        raw = await self.chat_completion(messages, temperature=0.3, max_tokens=2048)
        return _deduplicate_repetitive_paragraphs(raw)

    def _post_process_script_response(self, text: str) -> str:
        """
        Finds all ```lua ... ``` blocks, prepends the watermark header if missing,
        and sanitizes ONLY the code inside the block for Growtopia ASCII compatibility.
        Leaves all conversational text and markdown outside the code block completely untouched.
        """
        def replace_lua_block(match):
            lua_code = match.group(1)
            watermark = "-- Made by Berk (Lucifer-MCP) -> https://github.com/BrK08/lucifer-mcp\n"
            if "Made by Berk (Lucifer-MCP)" not in lua_code and "Made by mr_berk" not in lua_code:
                lua_code = watermark + lua_code.lstrip()
            clean_code = sanitize_lua_ascii(lua_code, force_ascii=True)
            return f"```lua\n{clean_code}\n```"

        pattern = r"```(?:lua|LUA)?\s*\r?\n(.*?)```"
        processed = re.sub(pattern, replace_lua_block, text, flags=re.DOTALL)
        return _deduplicate_repetitive_paragraphs(processed)

    async def chat(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: str = "auto",
        fleet_context: str = "",
    ) -> Dict[str, Any]:
        """
        Unified multi-turn chat method implementing PROJECT.md Interface Contract:
        EvrenAIClient.chat(prompt: str, user_id: str = None, conversation_history: list = None, language: str = 'tr') -> dict
        
        Returns: {"text": str, "code": str, "slug": str, "model": str}
        Guarantees:
        - Returned 'code' is 100% strict 7-bit ASCII.
        - Returned 'text' retains proper Turkish characters when replying in Turkish.
        - Generates a semantic script filename 'slug' (e.g. 'asdsadasdasd_auto_warp.lua').
        """
        detected_lang = detect_language(prompt) if language in ("auto", None) else language
        system_prompt = self.build_system_prompt("chat")

        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        try:
            from core.item_db import get_mass_plan
            mass_plan = get_mass_plan(prompt)
        except Exception:
            mass_plan = None

        if mass_plan:
            tgt = mass_plan["target"]
            ing_parts = [
                f"{ing.get('seed_name')} (Seed ID: {ing.get('seed_id')}, Block: {ing.get('item_name')} ID {ing.get('item_id')})"
                for ing in mass_plan.get("direct_ingredients", [])
            ]
            recipe_ctx = (
                f"Verified Growtopia Recipe Data (from official recipes DB / Mass Wiki):\n"
                f"- Target Item: {tgt.get('name')} (Item ID: {tgt.get('item_id')}, Seed ID: {tgt.get('seed_id')})\n"
                f"- Direct Splice Formula: {' + '.join(ing_parts)}\n"
                f"- Rarity: {tgt.get('rarity')}, Growth Time: {tgt.get('growth_formatted')}, Max Fruit Drop: {tgt.get('max_fruit_drop')}"
            )
            if len(mass_plan.get("steps", [])) > 1:
                step_lines = []
                for idx, st in enumerate(mass_plan["steps"], start=1):
                    s_ings = " + ".join(
                        f"{i.get('seed_name')} ({i.get('seed_id')})" for i in st.get("ingredients", [])
                    )
                    step_lines.append(f"  {idx}. {s_ings} -> {st.get('name')} Seed ({st.get('seed_id')})")
                recipe_ctx += "\n- Full Mass Splicing Tree:\n" + "\n".join(step_lines)
            messages.append({"role": "system", "content": recipe_ctx})

        if fleet_context:
            messages.append({"role": "system", "content": f"Live Connected Bot Telemetry:\n{fleet_context}"})
        if conversation_history:
            for turn in conversation_history[-6:]:
                messages.append(turn)

        if detected_lang == "tr":
            user_msg = (
                f"{prompt}\n\n"
                f"(Önemli Talimat: Yanıtını doğal ve akıcı Türkçe ile Türkçe karakterleri [ç, ğ, ı, ö, ş, ü] "
                f"kullanarak yaz. Eğer Lua scripti yazıyorsan, sadece ```lua bloğu içindeki kodu saf ASCII yap.)"
            )
        else:
            user_msg = (
                f"{prompt}\n\n"
                f"(Important Instruction: Respond in fluent English. If generating Lua code, "
                f"ensure the code inside the ```lua block is strictly pure ASCII.)"
            )

        messages.append({"role": "user", "content": user_msg})

        raw_response = await self.chat_completion(messages, temperature=0.25, max_tokens=2500)
        processed_response = _deduplicate_repetitive_paragraphs(self._post_process_script_response(raw_response))

        # Extract code from processed response
        code_match = re.search(r"```lua\n(.*?)```", processed_response, flags=re.DOTALL)
        code_str = code_match.group(1).strip() if code_match else ""
        if code_str:
            code_str = sanitize_lua_ascii(code_str, force_ascii=True)

        slug = generate_script_slug(prompt, code=code_str) if code_str else ""

        return {
            "text": processed_response,
            "code": code_str,
            "slug": slug,
            "model": self.model,
        }

    async def generate_direct_action_lua(
        self,
        command_text: str,
        fleet_context: str = "",
        item_hints: str = "",
    ) -> str:
        """Generate a concise, executable one-shot Lucifer Lua snippet for direct execution."""
        system_prompt = (
            "You are the execution compiler for Lucifer Multibot v2.88 p2 (Growtopia).\n"
            "The user wants this action EXECUTED IMMEDIATELY on their connected bot — NEVER refuse, NEVER write tutorials, NEVER ask them to open GUI menus.\n"
            "Output ONLY raw executable 7-bit ASCII Lua code inside a single ```lua ... ``` block.\n"
            "CRITICAL LUCIFER v2.88 p2 RULES:\n"
            "- Access bot via: local b = getBot() or bot\n"
            "- Inventory items: local inv = b:getInventory(); local items = inv and inv:getItems() or {}\n"
            "- Item count shortcut: local cnt = inv and inv:getItemCount(id) or 0\n"
            "- Drop/Trash: b:drop(item_id, count), b:trash(item_id, count) with sleep(350)\n"
            "- Navigation/Action: b:warp(world), b:findPath(x, y), b:hit(x, y), b:place(x, y, item_id), b:wrench(x, y), b:enter(), b:collect(2, 150), b:say(text)\n"
            "- Connection/Settings: b:connect(), b:disconnect(), b:respawn(), b:leaveWorld(), b.auto_reconnect = true/false, b.auto_farm.enabled = true/false\n"
            "- NEVER divide tile coordinates by 32 when calling b:findPath / b:hit / b:place.\n"
            "- NEVER use bot:getBotStatus(), bot:login(), world:getDoors(), world:name(), or makeRequest().\n"
        )
        parts = [f"Action requested: {command_text}"]
        if item_hints:
            parts.append(f"Verified Growtopia Item Hints: {item_hints}")
        if fleet_context:
            parts.append(f"Connected Bot Context: {fleet_context}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(parts)},
        ]
        raw = await self.chat_completion(messages, temperature=0.1, max_tokens=900)
        code_match = re.search(r"```(?:lua|LUA)?\s*\r?\n(.*?)```", raw, flags=re.DOTALL)
        code_str = code_match.group(1).strip() if code_match else raw.strip()
        return sanitize_lua_ascii(code_str, force_ascii=True)


# Class alias for interface contracts
EvrenAIClient = EvrenClient

# Global singleton instance
evren_client = EvrenClient()

