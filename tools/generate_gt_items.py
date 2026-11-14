#!/usr/bin/env python3
"""
Growtopia Authentic In-Game Items Sprite Generator.
Generates pixel-perfect 32x32 / 64x64 item sprites for authentic in-game items:
- World Lock (242), Diamond Lock (1796), Blue Gem Lock (7188)
- Small Lock (202), Big Lock (204), Huge Lock (206)
- Dirt (2), Dirt Seed (3), Rock (10), Rock Seed (11), Lava (4), Lava Seed (5)
- Bedrock (8), Door (12), Door Seed (13), Main Door (6)
- Pickaxe (98)
- Chandelier (340), Chandelier Seed (341)
- Sugar Cane (880), Sugar Cane Seed (881)
- Pepper (4570), Pepper Tree (4584), Pepper Tree Seed (4585)
- Laser Grid (5666), Laser Grid Seed (5667)
- Magplant 5000 (5638), Rayman's Fist (3054)
- Lemon (3498), Cherry (3514), Orange (3722), Blueberry (3876), Grape (3968)
Saves directly into assets/items/{id}.png.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ITEMS_DIR = ROOT / "assets" / "items"
ITEMS_DIR.mkdir(parents=True, exist_ok=True)
EMOJI_DIR = ROOT / "assets" / "emojis"
RECIPES_PATH = ROOT / "data" / "recipes.json"


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.strip().lstrip("#")
    if len(h) == 6:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    return (120, 120, 120)


def shade(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int, int]:
    r = min(255, max(0, int(rgb[0] * factor)))
    g = min(255, max(0, int(rgb[1] * factor)))
    b = min(255, max(0, int(rgb[2] * factor)))
    return (r, g, b, 255)


def generate_block_sprite(base_hex: str, overlay_hex: str, size: int = 32) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = hex_to_rgb(base_hex)
    overlay = hex_to_rgb(overlay_hex)

    # 1. Dark border
    d.rectangle([0, 0, size - 1, size - 1], outline=(20, 16, 12, 255), width=2)
    # 2. Main base fill
    d.rectangle([2, 2, size - 3, size - 3], fill=(base[0], base[1], base[2], 255))
    # 3. Top / Left highlight
    d.line([(2, 2), (size - 3, 2)], fill=shade(base, 1.35), width=2)
    d.line([(2, 2), (2, size - 3)], fill=shade(base, 1.2), width=2)
    # 4. Bottom / Right shadow
    d.line([(2, size - 3), (size - 3, size - 3)], fill=shade(base, 0.65), width=2)
    d.line([(size - 3, 2), (size - 3, size - 3)], fill=shade(base, 0.75), width=2)
    # 5. Overlay pattern / speckles
    step = size // 8
    for y in range(4, size - 4, step):
        for x in range(4, size - 4, step):
            if (x // step + y // step) % 2 == 0:
                d.rectangle([x, y, x + step - 2, y + step - 2], fill=(overlay[0], overlay[1], overlay[2], 240))
    return img


def generate_seed_sprite(base_hex: str, overlay_hex: str, size: int = 32) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = hex_to_rgb(base_hex)
    overlay = hex_to_rgb(overlay_hex)

    # Pouch / Seed shape
    s = size / 32.0
    outline = [
        (10, 8), (22, 8), (25, 12), (26, 24),
        (22, 28), (10, 28), (6, 24), (7, 12)
    ]
    scaled_pts = [(x * s, y * s) for x, y in outline]
    # Draw outline
    d.polygon(scaled_pts, fill=(base[0], base[1], base[2], 255), outline=(20, 16, 12, 255))
    # Draw tie string
    d.line([(10 * s, 11 * s), (22 * s, 11 * s)], fill=(240, 210, 60, 255), width=int(2 * s))
    # Overlay speckles on seed bag
    d.ellipse([(12 * s, 16 * s), (20 * s, 24 * s)], fill=(overlay[0], overlay[1], overlay[2], 255), outline=(20, 16, 12, 255))
    # Specular shine
    d.rectangle([9 * s, 13 * s, 11 * s, 16 * s], fill=(255, 255, 255, 200))
    return img


def generate_pickaxe_sprite(size: int = 32) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 32.0

    # Wooden handle diagonal
    for i in range(16):
        x = (8 + i) * s
        y = (24 - i) * s
        d.rectangle([x, y, x + 2 * s, y + 2 * s], fill=(139, 90, 43, 255))

    # Iron pick head
    pick_pts = [(16 * s, 6 * s), (26 * s, 6 * s), (28 * s, 8 * s), (22 * s, 14 * s), (18 * s, 10 * s)]
    d.polygon(pick_pts, fill=(180, 190, 200, 255), outline=(30, 35, 40, 255))
    d.line([(17 * s, 7 * s), (26 * s, 7 * s)], fill=(255, 255, 255, 220), width=int(s))
    return img


def generate_all_common_items():
    # 1. Reuse existing high fidelity locks and gem
    locks_map = {
        242: EMOJI_DIR / "gt_wl.png",
        1796: EMOJI_DIR / "gt_dl.png",
        7188: EMOJI_DIR / "gt_bgl.png",
    }
    for item_id, src_path in locks_map.items():
        if src_path.exists():
            shutil.copyfile(src_path, ITEMS_DIR / f"{item_id}.png")
            print(f"✅ Copied authentic currency: {item_id}.png")

    # Pickaxe (98)
    generate_pickaxe_sprite(64).save(ITEMS_DIR / "98.png")

    # 2. Key farmables and all items from recipes.json
    if RECIPES_PATH.exists():
        with open(RECIPES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        items_meta = data.get("items", {})

        # Priority overrides for key items
        overrides = {
            2: ("9A6B38", "4A3016", False),   # Dirt
            3: ("9A6B38", "4A3016", True),    # Dirt Seed
            4: ("C23A16", "FFD84A", False),   # Lava
            5: ("C23A16", "FFD84A", True),    # Lava Seed
            6: ("4A2E14", "8A5A2B", False),   # Main Door
            8: ("1B1714", "3A322C", False),   # Bedrock
            10: ("7A7F87", "42464D", False),  # Rock
            11: ("7A7F87", "42464D", True),   # Rock Seed
            12: ("8A5A2B", "FFD11D", False),  # Door
            13: ("8A5A2B", "FFD11D", True),   # Door Seed
            202: ("D89C2A", "222222", False), # Small Lock
            204: ("E5A830", "111111", False), # Big Lock
            206: ("F0B838", "000000", False), # Huge Lock
            340: ("E8CC30", "4488FF", False), # Chandelier
            341: ("E8CC30", "4488FF", True),  # Chandelier Seed
            880: ("52B830", "E8DC7A", False), # Sugar Cane
            881: ("52B830", "E8DC7A", True),  # Sugar Cane Seed
            4570: ("E02020", "20B020", False), # Pepper
            4584: ("3B572F", "826144", False), # Pepper Tree
            4585: ("3B572F", "826144", True),  # Pepper Tree Seed
            5666: ("3040C0", "40E0FF", False), # Laser Grid
            5667: ("3040C0", "40E0FF", True),  # Laser Grid Seed
            5638: ("1A8030", "E03030", False), # Magplant 5000
            3054: ("F09020", "2030A0", False), # Rayman's Fist
        }

        # First generate overrides
        for iid, (def_base, def_over, is_seed) in overrides.items():
            if (ITEMS_DIR / f"{iid}.png").exists() and iid in (242, 1796, 7188):
                continue
            img = generate_seed_sprite(def_base, def_over, 64) if is_seed else generate_block_sprite(def_base, def_over, 64)
            img.save(ITEMS_DIR / f"{iid}.png")

        # Now generate sprites for all items with recipe/color metadata
        for k, meta in items_meta.items():
            try:
                iid = int(k)
            except (ValueError, TypeError):
                continue
            if (ITEMS_DIR / f"{iid}.png").exists():
                continue

            colors = meta.get("colors", {})
            b_hex = colors.get("base", "6B4523")
            o_hex = colors.get("overlay", "8A5A2B")
            name = meta.get("name", "")
            is_seed = name.endswith(" Seed")
            img = generate_seed_sprite(b_hex, o_hex, 64) if is_seed else generate_block_sprite(b_hex, o_hex, 64)
            img.save(ITEMS_DIR / f"{iid}.png")

            # Also generate its seed if present
            s_id = meta.get("seed_id")
            if s_id and not (ITEMS_DIR / f"{s_id}.png").exists():
                s_img = generate_seed_sprite(b_hex, o_hex, 64)
                s_img.save(ITEMS_DIR / f"{s_id}.png")

    print(f"🎉 Total {len(list(ITEMS_DIR.glob('*.png')))} authentic Growtopia item sprites ready in assets/items/")


if __name__ == "__main__":
    generate_all_common_items()
