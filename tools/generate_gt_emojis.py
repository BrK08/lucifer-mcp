#!/usr/bin/env python3
"""
Growtopia Authentic Pixel Sprite Generator for Discord Emojis & Web Deck.
Generates pixel-perfect 64x64 RGBA icons matching Growtopia's authentic art style:
- gt_gem.png : Authentic multi-faceted red gemstone with crystal facets & shine
- gt_wl.png  : Authentic World Lock (gold casing with green globe center)
- gt_dl.png  : Authentic Diamond Lock (cyan diamond casing with crystal reflections)
- gt_bgl.png : Authentic Blue Gem Lock (deep sapphire blue lock with radiant core)
- gt_online.png : Glowing green status orb
- gt_offline.png: Dim red offline status orb
"""
from __future__ import annotations
import os
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
EMOJI_DIR = ROOT / "assets" / "emojis"
EMOJI_DIR.mkdir(parents=True, exist_ok=True)


def draw_pixel(draw: ImageDraw.Draw, x: int, y: int, color: tuple, scale: int = 4):
    draw.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1], fill=color)


def generate_gt_gem(scale: int = 4) -> Image.Image:
    """Generates authentic Growtopia multi-faceted Gem."""
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Color palette
    OL = (28, 6, 12, 255)       # Outline
    WHT = (255, 255, 255, 255)  # Specular shine
    LGT = (255, 130, 110, 255)  # Light table / gleam facet
    MID1 = (245, 55, 50, 255)   # Vivid red
    MID2 = (215, 25, 35, 255)   # Base ruby red
    DK1 = (165, 12, 24, 255)    # Shadow facet
    DK2 = (110, 5, 15, 255)     # Deep shadow pavilion

    # Grid (16x16)
    # y=2
    for x in range(5, 11): draw_pixel(d, x, 2, OL, scale)
    # y=3
    draw_pixel(d, 4, 3, OL, scale)
    draw_pixel(d, 5, 3, LGT, scale)
    draw_pixel(d, 6, 3, WHT, scale)
    for x in range(7, 11): draw_pixel(d, x, 3, LGT, scale)
    draw_pixel(d, 11, 3, OL, scale)
    # y=4
    draw_pixel(d, 3, 4, OL, scale)
    draw_pixel(d, 4, 4, LGT, scale)
    draw_pixel(d, 5, 4, WHT, scale)
    draw_pixel(d, 6, 4, WHT, scale)
    for x in range(7, 12): draw_pixel(d, x, 4, MID1, scale)
    draw_pixel(d, 12, 4, OL, scale)
    # y=5
    draw_pixel(d, 2, 5, OL, scale)
    draw_pixel(d, 3, 5, LGT, scale)
    draw_pixel(d, 4, 5, WHT, scale)
    for x in range(5, 8): draw_pixel(d, x, 5, MID1, scale)
    for x in range(8, 13): draw_pixel(d, x, 5, MID2, scale)
    draw_pixel(d, 13, 5, OL, scale)
    # y=6
    draw_pixel(d, 2, 6, OL, scale)
    draw_pixel(d, 3, 6, LGT, scale)
    for x in range(4, 8): draw_pixel(d, x, 6, MID1, scale)
    for x in range(8, 13): draw_pixel(d, x, 6, MID2, scale)
    draw_pixel(d, 13, 6, OL, scale)
    # y=7
    draw_pixel(d, 2, 7, OL, scale)
    for x in range(3, 7): draw_pixel(d, x, 7, MID1, scale)
    for x in range(7, 11): draw_pixel(d, x, 7, MID2, scale)
    for x in range(11, 13): draw_pixel(d, x, 7, DK1, scale)
    draw_pixel(d, 13, 7, OL, scale)
    # y=8
    draw_pixel(d, 2, 8, OL, scale)
    for x in range(3, 6): draw_pixel(d, x, 8, MID1, scale)
    for x in range(6, 10): draw_pixel(d, x, 8, MID2, scale)
    for x in range(10, 13): draw_pixel(d, x, 8, DK1, scale)
    draw_pixel(d, 13, 8, OL, scale)
    # y=9
    draw_pixel(d, 3, 9, OL, scale)
    for x in range(4, 7): draw_pixel(d, x, 9, MID2, scale)
    for x in range(7, 10): draw_pixel(d, x, 9, DK1, scale)
    for x in range(10, 12): draw_pixel(d, x, 9, DK2, scale)
    draw_pixel(d, 12, 9, OL, scale)
    # y=10
    draw_pixel(d, 4, 10, OL, scale)
    for x in range(5, 8): draw_pixel(d, x, 10, MID2, scale)
    for x in range(8, 10): draw_pixel(d, x, 10, DK1, scale)
    draw_pixel(d, 10, 10, DK2, scale)
    draw_pixel(d, 11, 10, OL, scale)
    # y=11
    draw_pixel(d, 5, 11, OL, scale)
    for x in range(6, 8): draw_pixel(d, x, 11, DK1, scale)
    for x in range(8, 10): draw_pixel(d, x, 11, DK2, scale)
    draw_pixel(d, 10, 11, OL, scale)
    # y=12
    draw_pixel(d, 6, 12, OL, scale)
    draw_pixel(d, 7, 12, DK1, scale)
    draw_pixel(d, 8, 12, DK2, scale)
    draw_pixel(d, 9, 12, OL, scale)
    # y=13
    draw_pixel(d, 7, 13, OL, scale)
    draw_pixel(d, 8, 13, OL, scale)

    return img


def generate_gt_wl(scale: int = 4) -> Image.Image:
    """Generates authentic Growtopia World Lock (Item ID 242)."""
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    OL = (25, 20, 10, 255)
    GLD_LGT = (255, 235, 110, 255)
    GLD_MID = (245, 195, 45, 255)
    GLD_DK = (195, 140, 20, 255)
    GLD_DEEP = (135, 90, 10, 255)
    BLU = (60, 140, 240, 255)
    GRN = (60, 190, 70, 255)
    WHT = (255, 255, 255, 255)

    # Shackle
    for x in range(5, 11): draw_pixel(d, x, 1, OL, scale)
    for y in range(2, 6):
        draw_pixel(d, 4, y, OL, scale)
        draw_pixel(d, 5, y, GLD_LGT, scale)
        draw_pixel(d, 10, y, GLD_DK, scale)
        draw_pixel(d, 11, y, OL, scale)

    # Body base
    for x in range(2, 14): draw_pixel(d, x, 6, OL, scale)
    for y in range(7, 15):
        draw_pixel(d, 1, y, OL, scale)
        draw_pixel(d, 14, y, OL, scale)
    for x in range(2, 14): draw_pixel(d, x, 15, OL, scale)

    # Body fill
    for y in range(7, 15):
        for x in range(2, 14):
            if y == 7 or x == 2:
                draw_pixel(d, x, y, GLD_LGT, scale)
            elif y == 14 or x == 13:
                draw_pixel(d, x, y, GLD_DEEP, scale)
            else:
                draw_pixel(d, x, y, GLD_MID, scale)

    # Earth globe in center (4x4)
    for gy in range(9, 13):
        for gx in range(5, 11):
            draw_pixel(d, gx, gy, BLU, scale)
    # Continents
    draw_pixel(d, 6, 9, GRN, scale)
    draw_pixel(d, 7, 9, GRN, scale)
    draw_pixel(d, 6, 10, GRN, scale)
    draw_pixel(d, 9, 10, GRN, scale)
    draw_pixel(d, 8, 11, GRN, scale)
    draw_pixel(d, 9, 11, GRN, scale)
    draw_pixel(d, 7, 12, GRN, scale)

    # Highlights
    draw_pixel(d, 3, 7, WHT, scale)
    draw_pixel(d, 4, 7, WHT, scale)
    draw_pixel(d, 3, 8, WHT, scale)

    return img


def generate_gt_dl(scale: int = 4) -> Image.Image:
    """Generates authentic Growtopia Diamond Lock (Item ID 1796)."""
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    OL = (15, 25, 35, 255)
    CYAN_WHT = (230, 250, 255, 255)
    CYAN_LGT = (140, 235, 255, 255)
    CYAN_MID = (70, 195, 245, 255)
    CYAN_DK = (35, 140, 195, 255)
    CYAN_DEEP = (18, 85, 135, 255)
    WHT = (255, 255, 255, 255)

    # Shackle
    for x in range(5, 11): draw_pixel(d, x, 1, OL, scale)
    for y in range(2, 6):
        draw_pixel(d, 4, y, OL, scale)
        draw_pixel(d, 5, y, CYAN_WHT, scale)
        draw_pixel(d, 10, y, CYAN_DK, scale)
        draw_pixel(d, 11, y, OL, scale)

    # Body Outline
    for x in range(2, 14): draw_pixel(d, x, 6, OL, scale)
    for y in range(7, 15):
        draw_pixel(d, 1, y, OL, scale)
        draw_pixel(d, 14, y, OL, scale)
    for x in range(2, 14): draw_pixel(d, x, 15, OL, scale)

    # Body Fill with Diamond Facets
    for y in range(7, 15):
        for x in range(2, 14):
            if y == 7 or x == 2:
                draw_pixel(d, x, y, CYAN_LGT, scale)
            elif y == 14 or x == 13:
                draw_pixel(d, x, y, CYAN_DEEP, scale)
            else:
                draw_pixel(d, x, y, CYAN_MID, scale)

    # Diamond centerpiece
    for dy in range(9, 13):
        for dx in range(5, 11):
            draw_pixel(d, dx, dy, CYAN_DK, scale)
    draw_pixel(d, 7, 9, CYAN_WHT, scale)
    draw_pixel(d, 8, 9, CYAN_WHT, scale)
    draw_pixel(d, 6, 10, CYAN_WHT, scale)
    draw_pixel(d, 7, 10, WHT, scale)
    draw_pixel(d, 8, 10, CYAN_LGT, scale)
    draw_pixel(d, 9, 10, CYAN_LGT, scale)
    draw_pixel(d, 7, 11, CYAN_LGT, scale)
    draw_pixel(d, 8, 11, CYAN_MID, scale)

    # Gleam
    draw_pixel(d, 3, 7, WHT, scale)
    draw_pixel(d, 4, 7, WHT, scale)
    draw_pixel(d, 3, 8, WHT, scale)

    return img


def generate_gt_bgl(scale: int = 4) -> Image.Image:
    """Generates authentic Growtopia Blue Gem Lock (Item ID 7188)."""
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    OL = (8, 12, 28, 255)
    B_WHT = (220, 240, 255, 255)
    B_LGT = (100, 175, 255, 255)
    B_MID = (45, 105, 235, 255)
    B_DK = (20, 60, 175, 255)
    B_DEEP = (10, 30, 110, 255)
    WHT = (255, 255, 255, 255)

    # Shackle
    for x in range(5, 11): draw_pixel(d, x, 1, OL, scale)
    for y in range(2, 6):
        draw_pixel(d, 4, y, OL, scale)
        draw_pixel(d, 5, y, B_WHT, scale)
        draw_pixel(d, 10, y, B_DK, scale)
        draw_pixel(d, 11, y, OL, scale)

    # Body Outline
    for x in range(2, 14): draw_pixel(d, x, 6, OL, scale)
    for y in range(7, 15):
        draw_pixel(d, 1, y, OL, scale)
        draw_pixel(d, 14, y, OL, scale)
    for x in range(2, 14): draw_pixel(d, x, 15, OL, scale)

    # Body Fill
    for y in range(7, 15):
        for x in range(2, 14):
            if y == 7 or x == 2:
                draw_pixel(d, x, y, B_LGT, scale)
            elif y == 14 or x == 13:
                draw_pixel(d, x, y, B_DEEP, scale)
            else:
                draw_pixel(d, x, y, B_MID, scale)

    # Sapphire core
    for dy in range(9, 13):
        for dx in range(5, 11):
            draw_pixel(d, dx, dy, B_DK, scale)
    draw_pixel(d, 7, 9, B_WHT, scale)
    draw_pixel(d, 8, 9, B_WHT, scale)
    draw_pixel(d, 7, 10, WHT, scale)
    draw_pixel(d, 8, 10, B_LGT, scale)

    # Gleam
    draw_pixel(d, 3, 7, WHT, scale)
    draw_pixel(d, 4, 7, WHT, scale)
    draw_pixel(d, 3, 8, WHT, scale)

    return img


def generate_status_icon(is_online: bool, scale: int = 4) -> Image.Image:
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    center = size // 2
    radius = 5 * scale
    color = (80, 225, 60, 255) if is_online else (240, 50, 45, 255)
    border = (15, 50, 10, 255) if is_online else (50, 10, 10, 255)

    d.ellipse([center - radius - scale, center - radius - scale, center + radius + scale, center + radius + scale], fill=border)
    d.ellipse([center - radius, center - radius, center + radius, center + radius], fill=color)
    d.ellipse([center - radius // 2, center - radius // 2, center, center], fill=(255, 255, 255, 200))
    return img


def generate_gt_seed(scale: int = 4) -> Image.Image:
    """Generates authentic Growtopia Tree Seed icon."""
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    OL = (24, 18, 10, 255)
    WOOD_L = (195, 138, 72, 255)
    WOOD_M = (150, 96, 42, 255)
    WOOD_D = (102, 60, 22, 255)
    LEAF_L = (120, 230, 85, 255)
    LEAF_M = (65, 185, 50, 255)
    LEAF_D = (35, 125, 30, 255)

    # Sprout leaves on top
    for x, y, c in [
        (6, 2, LEAF_L), (7, 2, LEAF_L), (8, 2, LEAF_M),
        (5, 3, LEAF_L), (6, 3, LEAF_L), (7, 3, LEAF_M), (9, 3, LEAF_L), (10, 3, LEAF_M),
        (6, 4, LEAF_M), (7, 4, LEAF_D), (8, 4, LEAF_M), (9, 4, LEAF_M),
        (7, 5, LEAF_D), (8, 5, LEAF_D),
    ]:
        draw_pixel(d, x, y, c, scale)

    # Seed pod body (teardrop/oval)
    pod_rows = {
        6: (6, 9),
        7: (5, 10),
        8: (4, 11),
        9: (4, 11),
        10: (4, 11),
        11: (5, 10),
        12: (5, 10),
        13: (6, 9),
        14: (7, 8),
    }
    for y, (x0, x1) in pod_rows.items():
        draw_pixel(d, x0 - 1, y, OL, scale)
        draw_pixel(d, x1 + 1, y, OL, scale)
        for x in range(x0, x1 + 1):
            if x <= x0 + 1 and y <= 10:
                draw_pixel(d, x, y, WOOD_L, scale)
            elif x >= x1 - 1 or y >= 13:
                draw_pixel(d, x, y, WOOD_D, scale)
            else:
                draw_pixel(d, x, y, WOOD_M, scale)
    for x in range(6, 10):
        draw_pixel(d, x, 5, OL, scale)
    draw_pixel(d, 7, 15, OL, scale)
    draw_pixel(d, 8, 15, OL, scale)
    return img


def generate_all():
    sprites = {
        "gt_gem.png": generate_gt_gem(4),
        "gt_wl.png": generate_gt_wl(4),
        "gt_dl.png": generate_gt_dl(4),
        "gt_bgl.png": generate_gt_bgl(4),
        "gt_seed.png": generate_gt_seed(4),
        "gt_online.png": generate_status_icon(True, 4),
        "gt_offline.png": generate_status_icon(False, 4),
    }

    for filename, img in sprites.items():
        out_path = EMOJI_DIR / filename
        img.save(out_path)
        print(f"✅ Generated authentic sprite: {out_path} ({img.width}x{img.height})")


if __name__ == "__main__":
    generate_all()
