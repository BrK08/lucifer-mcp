"""
Lucifer Multibot — Growtopia Item Database & Search Engine
Provides item ID lookup, name search, seed pairs, splicing recipes, growth times, and in-game colors.
Powered by 6,832 authentic Growtopia items from items.json & recipes.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

ROOT = Path(__file__).resolve().parent.parent
ITEMS_DATA_PATH = ROOT / "data" / "items.json"
RECIPES_DATA_PATH = ROOT / "data" / "recipes.json"

_ITEMS_BY_ID: Dict[int, str] = {}
_NAME_TO_ID: Dict[str, int] = {}
_SEED_OF: Dict[int, int] = {}
_BLOCK_OF: Dict[int, int] = {}
_RECIPES_BY_ID: Dict[int, Dict[str, Any]] = {}
_INITIALIZED: bool = False


def _init_db():
    global _ITEMS_BY_ID, _NAME_TO_ID, _SEED_OF, _BLOCK_OF, _RECIPES_BY_ID, _INITIALIZED
    if _INITIALIZED:
        return

    # 1. Load basic items mapping
    if ITEMS_DATA_PATH.exists():
        try:
            with open(ITEMS_DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.get("items", {}).items():
                try:
                    iid = int(k)
                    _ITEMS_BY_ID[iid] = v
                    name_lower = v.lower()
                    if name_lower not in _NAME_TO_ID:
                        _NAME_TO_ID[name_lower] = iid
                except (ValueError, TypeError):
                    continue
        except Exception as e:
            print(f"[ItemDB] Error loading items.json: {e}")

    # 2. Load rich recipes & metadata
    if RECIPES_DATA_PATH.exists():
        try:
            with open(RECIPES_DATA_PATH, "r", encoding="utf-8") as f:
                rdata = json.load(f)
            for k, meta in rdata.get("items", {}).items():
                try:
                    iid = int(k)
                    _RECIPES_BY_ID[iid] = meta
                    s_id = meta.get("seed_id")
                    if s_id is not None:
                        _SEED_OF[iid] = int(s_id)
                        _BLOCK_OF[int(s_id)] = iid
                except (ValueError, TypeError):
                    continue
        except Exception as e:
            print(f"[ItemDB] Error loading recipes.json: {e}")

    # Ensure modern high-tier currencies and essential aliases
    if 7188 not in _ITEMS_BY_ID:
        _ITEMS_BY_ID[7188] = "Blue Gem Lock"
        _NAME_TO_ID["blue gem lock"] = 7188
    _NAME_TO_ID["bgl"] = 7188
    _NAME_TO_ID["dl"] = 1796
    _NAME_TO_ID["wl"] = 242

    # 3. Derive standard seed pairs if not in recipes
    for iid, name in _ITEMS_BY_ID.items():
        if name.endswith(" Seed") and _ITEMS_BY_ID.get(iid - 1) == name[:-5]:
            if (iid - 1) not in _SEED_OF:
                _SEED_OF[iid - 1] = iid
                _BLOCK_OF[iid] = iid - 1

    _INITIALIZED = True


_init_db()


def get_item_name(item_id: int) -> str:
    """Returns the authentic in-game item name for an ID, or 'Unknown Item'."""
    _init_db()
    return _ITEMS_BY_ID.get(item_id, f"Unknown Item ({item_id})")


def get_item_id(item_name: str) -> Optional[int]:
    """Finds exact item ID by name (case-insensitive)."""
    _init_db()
    return _NAME_TO_ID.get(item_name.strip().lower())


def get_seed_id(block_id: int) -> Optional[int]:
    """Returns the verified seed ID for a block ID."""
    _init_db()
    return _SEED_OF.get(block_id)


def get_block_id(seed_id: int) -> Optional[int]:
    """Returns the verified block ID for a seed ID."""
    _init_db()
    return _BLOCK_OF.get(seed_id)


def get_item_details(id_or_name: int | str) -> Optional[Dict[str, Any]]:
    """Returns comprehensive Growtopia in-game details: rarity, recipe, growth time, colors."""
    _init_db()
    if isinstance(id_or_name, int):
        iid = id_or_name
    elif isinstance(id_or_name, str):
        if id_or_name.isdigit():
            iid = int(id_or_name)
        else:
            iid = get_item_id(id_or_name)
            if iid is None:
                return None
    else:
        return None

    name = get_item_name(iid)
    recipe_meta = _RECIPES_BY_ID.get(iid, {})

    is_seed = name.endswith(" Seed")
    seed_id = _SEED_OF.get(iid)
    block_id = _BLOCK_OF.get(iid)

    return {
        "id": iid,
        "name": name,
        "is_seed": is_seed,
        "seed_id": seed_id,
        "block_id": block_id,
        "rarity": recipe_meta.get("rarity"),
        "tier": recipe_meta.get("tier"),
        "category": recipe_meta.get("category", "Seed" if is_seed else "Block"),
        "growth_seconds": recipe_meta.get("growth_seconds"),
        "growth_formatted": recipe_meta.get("growth_formatted"),
        "max_fruit_drop": recipe_meta.get("max_fruit_drop"),
        "colors": recipe_meta.get("colors", {}),
        "recipe": recipe_meta.get("recipe", {}),
    }


def search_items(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Searches items matching query string."""
    _init_db()
    q = query.strip().lower()
    results = []
    for iid, name in _ITEMS_BY_ID.items():
        if q in name.lower() or (q.isdigit() and str(iid) == q):
            seed_id = _SEED_OF.get(iid)
            meta = _RECIPES_BY_ID.get(iid, {})
            results.append({
                "id": iid,
                "name": name,
                "is_seed": name.endswith(" Seed"),
                "seed_id": seed_id,
                "rarity": meta.get("rarity"),
                "category": meta.get("category"),
            })
            if len(results) >= limit:
                break
    return results


_COMMON_ITEM_ALIASES: Dict[str, int] = {
    "dirt": 2,
    "toprak": 2,
    "dirt seed": 3,
    "toprak tohumu": 3,
    "lava": 4,
    "lav": 4,
    "lava seed": 5,
    "rock": 10,
    "kaya": 10,
    "tas": 10,
    "cave dirt": 14,
    "cave background": 14,
    "pickaxe": 98,
    "kazma": 98,
    "wl": 242,
    "wls": 242,
    "world lock": 242,
    "sl": 202,
    "small lock": 202,
    "bl": 204,
    "big lock": 204,
    "hl": 206,
    "huge lock": 206,
    "chand": 340,
    "chandelier": 340,
    "dl": 1796,
    "dls": 1796,
    "diamond lock": 1796,
    "vend": 2978,
    "vending machine": 2978,
    "pepper": 4584,
    "pepper tree": 4584,
    "pepper seed": 4585,
    "fish tank": 3004,
    "fishtank": 3004,
    "ftank": 3004,
    "magplant": 5638,
    "lgrid": 5666,
    "laser grid": 5666,
    "laser grid seed": 5667,
    "gaut": 6946,
    "rayman": 5480,
    "bgl": 7188,
    "bgls": 7188,
    "blue gem lock": 7188,
}


def resolve_item_fuzzy(query: str) -> Optional[Dict[str, Any]]:
    """
    Resolve natural Turkish/English item phrases (e.g. 'dirti', 'world locku', 'pepperları', '242')
    to {'id': int, 'name': str}.
    """
    _init_db()
    if not query or not isinstance(query, str):
        return None

    raw = (
        query.strip()
        .lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace("'", "")
        .replace("’", "")
        .replace('"', "")
    )
    for noise in ("tane", "adet", "itemi", "item", "esyayi", "esya", "bloku", "blok", "block"):
        raw = re.sub(rf"\b{noise}\b", " ", raw)
    cleaned = re.sub(r"\s+", " ", raw).strip(" .,!?:-_")
    if not cleaned:
        return None

    if cleaned.isdigit():
        iid = int(cleaned)
        if iid in _ITEMS_BY_ID:
            return {"id": iid, "name": _ITEMS_BY_ID[iid]}
        return None

    # Build suffix-stripped candidates to handle Turkish case endings (-i, -yi, -leri, -dan, etc.)
    suffixes = (
        "larini", "lerini", "lari", "leri", "lardan", "lerden",
        "lar", "ler", "yiyi", "yi", "yu", "ye", "ya",
        "dan", "den", "tan", "ten", "nin", "nun",
        "i", "u", "a", "e", "s",
    )
    candidates = [cleaned]
    for suf in suffixes:
        if len(cleaned) > len(suf) + 1 and cleaned.endswith(suf):
            candidates.append(cleaned[: -len(suf)].strip())

    # If multi-word, also try the trailing noun and seed conversion
    for cand in list(candidates):
        if cand.endswith(" tohumu") or cand.endswith(" tohum"):
            stem = cand.rsplit(" ", 1)[0].strip()
            candidates.append(f"{stem} seed")

    for cand in candidates:
        if cand in _COMMON_ITEM_ALIASES:
            iid = _COMMON_ITEM_ALIASES[cand]
            return {"id": iid, "name": get_item_name(iid)}
        if cand in _NAME_TO_ID:
            iid = _NAME_TO_ID[cand]
            return {"id": iid, "name": get_item_name(iid)}

    # Substring fallback from shortest cleaned stem
    for cand in candidates:
        if len(cand) < 2:
            continue
        matches = search_items(cand, limit=8)
        if matches:
            # Prefer exact prefix or shorter canonical block/item name
            matches.sort(key=lambda m: (0 if m["name"].lower().startswith(cand) else 1, len(m["name"])))
            best = matches[0]
            return {"id": best["id"], "name": best["name"]}

    return None


def get_all_items_catalog() -> Dict[str, Any]:
    """Returns full catalog dictionary optimized for Web Deck caching."""
    _init_db()
    catalog = {}
    for iid, name in _ITEMS_BY_ID.items():
        meta = _RECIPES_BY_ID.get(iid, {})
        is_seed = name.endswith(" Seed")
        catalog[iid] = {
            "n": name,
            "k": "SEED" if is_seed else ("CURRENCY" if iid in (242, 1796, 7188, 202, 204, 206) else "BLOCK"),
            "sid": _SEED_OF.get(iid),
            "bid": _BLOCK_OF.get(iid),
            "r": meta.get("rarity"),
            "c": meta.get("colors", {}).get("base", "6B4523"),
        }
    return catalog


def get_splicing_recipe(id_or_name: Union[int, str]) -> Optional[Dict[str, Any]]:
    """
    Returns authentic Growtopia splicing recipe metadata from recipes.json
    for a given block/item/seed ID or name.
    """
    _init_db()
    iid: Optional[int] = None
    if isinstance(id_or_name, int) and not isinstance(id_or_name, bool):
        iid = id_or_name
    elif isinstance(id_or_name, str):
        s = id_or_name.strip()
        if s.isdigit():
            iid = int(s)
        else:
            exact = get_item_id(s)
            if exact is not None:
                iid = exact
            else:
                fuzzy = resolve_item_fuzzy(s)
                if fuzzy:
                    iid = int(fuzzy["id"])

    if iid is None:
        return None

    # Map seed IDs to their parent block/tree item ID where recipes are stored.
    block_id = _BLOCK_OF.get(iid, iid)
    meta = _RECIPES_BY_ID.get(block_id) or _RECIPES_BY_ID.get(iid)
    if not isinstance(meta, dict):
        return None

    recipe_block = meta.get("recipe") or {}
    ingredients = recipe_block.get("ingredients") or []
    if not ingredients:
        return None

    seed_id = meta.get("seed_id", _SEED_OF.get(block_id))
    seed_name = meta.get("seed_name") or (get_item_name(int(seed_id)) if seed_id is not None else "")

    return {
        "item_id": int(meta.get("item_id", block_id)),
        "name": meta.get("name", get_item_name(block_id)),
        "seed_id": int(seed_id) if seed_id is not None else None,
        "seed_name": seed_name,
        "rarity": meta.get("rarity"),
        "tier": meta.get("tier"),
        "category": meta.get("category"),
        "growth_seconds": meta.get("growth_seconds"),
        "growth_formatted": meta.get("growth_formatted"),
        "max_fruit_drop": meta.get("max_fruit_drop"),
        "recipe_type": recipe_block.get("type", "SPLICE"),
        "output_siblings": list(recipe_block.get("output_siblings") or []),
        "ingredients": [dict(ing) for ing in ingredients],
    }


_MASS_QUERY_NOISE = {
    "mass", "massi", "massim", "masslar", "masslari", "yapmak", "yapcam", "yapacagim",
    "yaparim", "istiyorum", "istiyorumda", "icin", "hangi", "neler", "nelerdir",
    "seedlerden", "seedleri", "seedler", "seedi", "seed", "seeds",
    "tohumlardan", "tohumlari", "tohumlar", "tohumu", "tohum",
    "lazim", "gerek", "gerekli", "gereken", "gerekir",
    "envanterimde", "envanterim", "envanterde", "envanterindeki", "envanterdeki", "envanter",
    "cantamda", "cantada", "inventory", "olan", "varmi", "var", "yok", "mi", "mu", "mı",
    "nasil", "yapilir", "yapiliyor", "yapilirmi", "tarifi", "tarif", "recipe",
    "birlesim", "birlesimi", "birlesir", "birlesince", "birlestir", "splice", "splicing",
    "wiki", "wikideki", "growtopia", "kaynak", "kaynaga", "gore",
    "bot", "botta", "botumda", "botlar", "botlarda", "botlarimda",
    "ve", "veya", "ile", "da", "de", "bu", "bir", "su", "an", "ben", "bana", "benim",
    "make", "want", "which", "what", "needed", "need", "needs", "from", "how", "to",
    "ingredients", "check", "my", "have", "any", "do", "does", "in", "for", "the", "a",
}


def get_mass_plan(query: str, max_depth: int = 3) -> Optional[Dict[str, Any]]:
    """
    Resolves a natural-language mass/splicing query (e.g. 'door massı yapmak istiyorum...')
    into the target Growtopia splicing recipe, recursive multi-step mass tree, and required seeds.
    """
    _init_db()
    if not query or not isinstance(query, str):
        return None

    norm = (
        query.strip()
        .lower()
        .replace("ı", "i")
        .replace("İ", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    raw_tokens = [t for t in re.split(r"[^a-z0-9']+", norm) if t]
    # Strip trailing Turkish 'i' from tokens like 'massı' -> 'massi', keep alphanumeric tokens
    core_tokens = [t for t in raw_tokens if t not in _MASS_QUERY_NOISE]
    if not core_tokens:
        return None

    target_recipe: Optional[Dict[str, Any]] = None

    # First check exact multi-word / single-word item names & common aliases
    for span in range(min(4, len(core_tokens)), 0, -1):
        for idx in range(len(core_tokens) - span + 1):
            cand = " ".join(core_tokens[idx:idx + span])
            if cand in _COMMON_ITEM_ALIASES:
                rec = get_splicing_recipe(_COMMON_ITEM_ALIASES[cand])
                if rec:
                    target_recipe = rec
                    break
            if cand in _NAME_TO_ID:
                rec = get_splicing_recipe(_NAME_TO_ID[cand])
                if rec:
                    target_recipe = rec
                    break
        if target_recipe:
            break

    # Fallback to fuzzy resolution if no exact match had a recipe
    if target_recipe is None:
        for span in range(min(3, len(core_tokens)), 0, -1):
            for idx in range(len(core_tokens) - span + 1):
                cand = " ".join(core_tokens[idx:idx + span])
                fuzzy = resolve_item_fuzzy(cand)
                if fuzzy:
                    rec = get_splicing_recipe(int(fuzzy["id"]))
                    if rec:
                        target_recipe = rec
                        break
            if target_recipe:
                break

    if not target_recipe:
        return None

    steps: List[Dict[str, Any]] = []
    seen_steps = set()

    def _collect_steps(recipe_obj: Dict[str, Any], depth: int, ancestors: set) -> None:
        item_id = int(recipe_obj["item_id"])
        if depth < max_depth:
            for ing in recipe_obj.get("ingredients", []):
                ing_item_id = ing.get("item_id")
                if ing_item_id is None:
                    continue
                ing_id_int = int(ing_item_id)
                if ing_id_int in ancestors:
                    continue
                sub_rec = get_splicing_recipe(ing_id_int)
                if sub_rec:
                    _collect_steps(sub_rec, depth + 1, ancestors | {item_id})
        if item_id not in seen_steps:
            seen_steps.add(item_id)
            steps.append(recipe_obj)

    _collect_steps(target_recipe, 1, {int(target_recipe["item_id"])})

    required_seeds: List[Dict[str, Any]] = []
    seen_seed_ids = set()
    # Direct ingredients first, then any base seeds from earlier sub-steps
    for ing in target_recipe.get("ingredients", []):
        sid = ing.get("seed_id")
        if sid is not None and int(sid) not in seen_seed_ids:
            seen_seed_ids.add(int(sid))
            required_seeds.append(dict(ing))
    for st in steps:
        for ing in st.get("ingredients", []):
            sid = ing.get("seed_id")
            if sid is not None and int(sid) not in seen_seed_ids:
                seen_seed_ids.add(int(sid))
                required_seeds.append(dict(ing))

    return {
        "target": target_recipe,
        "direct_ingredients": list(target_recipe.get("ingredients", [])),
        "steps": steps,
        "required_seeds": required_seeds,
    }
