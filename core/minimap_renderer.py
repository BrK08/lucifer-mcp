"""
Lucifer Multibot — In-Game Minimap & World Visualizer (2D Canvas Renderer)
Renders 100x60 Growtopia world tile grids into 1:1 pixel-accurate minimap images (PNG)
identical to Lucifer client's native [Map] tab (with tabs, bot marker, lava, rock, dirt, and bedrock).
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont

try:
    from core.item_db import get_item_details
except ImportError:
    try:
        from item_db import get_item_details
    except ImportError:
        def get_item_details(item_id: int) -> Optional[Dict[str, Any]]:
            return None

# Canvas dimensions matching Lucifer v2.88 p2 [Map] GUI
TILE_W = 100
TILE_H = 60
TILE_PIXEL_SIZE = 5  # 5x5 pixels per tile (500x300 map area)

IMG_W = 544
IMG_H = 389
MAP_OFFSET_X = 22
MAP_OFFSET_Y = 62

LOCK_ITEM_IDS = {202, 204, 206, 240, 242, 1796, 2408, 4994, 7188, 9640, 10410}
DOOR_ITEM_IDS = {6, 12, 26, 28, 762, 858, 998, 1296, 1420, 1480, 1528, 1682}

# Exact color palette sampled directly from Lucifer v2.88 p2 runtime screenshot
COLOR_SKY = (0, 183, 235)         # Cyan sky (Air / Empty fg == 0)
COLOR_DIRT = (96, 57, 19)         # Soil / Dirt block (fg 2)
COLOR_CAVE_DIRT = (80, 48, 16)    # Cave Dirt (fg 14)
COLOR_ROCK = (125, 122, 119)      # Granite / Rock (fg 10)
COLOR_LAVA = (255, 40, 17)        # Molten Lava (fg 4)
COLOR_BEDROCK = (77, 63, 84)      # Dark Bedrock (fg 8)
COLOR_GOLD_LOCK = (255, 215, 0)   # World Lock / Locks (fg 242, 240, 202, 9640)
COLOR_TREE = (34, 197, 94)        # Trees / Crops / Seeds
COLOR_DOOR = (212, 165, 89)       # Main Door / Portals (fg 6, 26)
COLOR_BOT_MARKER = (238, 12, 15)  # Local Player / Bot position indicator
COLOR_OTHER_PLAYER = (255, 255, 255) # White dot for other players
COLOR_CONTOUR = (16, 22, 28)      # 1px Lucifer block outline against air

# Header & Background colors
COLOR_BG = (1, 15, 30)            # Deep dark navy frame
COLOR_HEADER_BG = (2, 25, 48)     # Header tab bar background
COLOR_ACTIVE_TAB = (8, 48, 86)    # Active [Map] tab
COLOR_TEXT = (220, 230, 242)      # Primary text color
COLOR_TEXT_DIM = (130, 150, 175)  # Dim text color
COLOR_TOGGLE_ON = (0, 183, 235)   # Toggle switch active color


def _parse_hex_rgb(hex_str: Any) -> Optional[Tuple[int, int, int]]:
    s = str(hex_str or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            return None
    if len(s) == 8:
        # Handle ARGB hex sometimes stored in item_db
        try:
            return (int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
        except ValueError:
            return None
    return None


def get_tile_color(fg: int, bg: int = 0) -> Tuple[int, int, int]:
    """Maps a Growtopia item ID to its authentic minimap color."""
    if fg <= 0 or fg == 14:
        return COLOR_SKY
    if fg in (2, 3):
        return COLOR_DIRT
    if fg == 15:
        return COLOR_TREE
    if fg in (10, 11):
        return COLOR_ROCK
    if fg in (4, 5):
        return COLOR_LAVA
    if fg == 8:
        return COLOR_BEDROCK
    if fg in LOCK_ITEM_IDS:
        return COLOR_GOLD_LOCK
    if fg in DOOR_ITEM_IDS:
        return COLOR_DOOR
    if fg in (102, 4580):  # Wood Platform, various platforms
        return (170, 130, 85)
    if fg in (822, 824):  # Water
        return (0, 119, 190)
    if fg in (5666, 5667):  # Laser Grid
        return (230, 50, 50)
    if fg in (4570, 4584, 340, 341):  # Pepper, Chand, etc.
        return COLOR_TREE
    if fg % 2 == 1:  # Seed/Tree item IDs in Growtopia
        return COLOR_TREE

    details = get_item_details(fg)
    if isinstance(details, dict):
        colors = details.get("colors")
        if isinstance(colors, dict):
            parsed = _parse_hex_rgb(colors.get("base"))
            if parsed and parsed != (0, 0, 0):
                return parsed

    h = (fg * 37) % 256
    return (max(50, (h * 3) % 220), max(40, (h * 5) % 200), max(40, (h * 7) % 210))


def _parse_tiles_arg(tiles: Optional[Union[List[int], Dict[str, int], str]]) -> Optional[List[int]]:
    """Normalize RLE string, comma string, or list into a flat tile FG list."""
    if isinstance(tiles, str):
        parsed: List[int] = []
        if ":" in tiles:
            for chunk in tiles.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                parts = chunk.split(":", 1)
                try:
                    fg_val = int(parts[0])
                    cnt_val = int(parts[1])
                    parsed.extend([fg_val] * cnt_val)
                except ValueError:
                    pass
        else:
            for item in tiles.split(","):
                item = item.strip()
                if item:
                    try:
                        parsed.append(int(item))
                    except ValueError:
                        pass
        return parsed
    if isinstance(tiles, list):
        out: List[int] = []
        for fg in tiles[: TILE_W * TILE_H]:
            if isinstance(fg, dict):
                out.append(int(fg.get("fg", 0) or 0))
            elif isinstance(fg, (int, float)):
                out.append(int(fg))
            else:
                out.append(0)
        return out
    return None


def extract_map_landmarks(
    tiles: Optional[Union[List[int], Dict[str, int], str]] = None,
    bot_x: int = 50,
    bot_y: int = 23,
    other_players: Optional[List[Any]] = None,
    max_items: int = 22,
    lang: str = "en",
) -> List[Dict[str, Any]]:
    """Extract clickable landmark coordinates from live world tiles and players."""
    is_tr = str(lang or "en").lower().startswith("tr")
    try:
        bx = int(bot_x)
        by = int(bot_y)
    except (ValueError, TypeError):
        bx, by = 50, 23
    if bx >= 100:
        bx //= 32
    if by >= 60:
        by //= 32
    bx = max(0, min(TILE_W - 1, bx))
    by = max(0, min(TILE_H - 1, by))

    landmarks: List[Dict[str, Any]] = [
        {"x": bx, "y": by, "kind": "bot", "fg": 0, "emoji": "🤖", "label": f"{'Bot Konumu' if is_tr else 'Bot Position'} ({bx}, {by})"},
        {"x": min(TILE_W - 1, bx + 1), "y": by, "kind": "adj", "fg": 0, "emoji": "➡️", "label": f"{'Botun Sağı' if is_tr else 'Right of Bot'} ({min(TILE_W - 1, bx + 1)}, {by})"},
        {"x": max(0, bx - 1), "y": by, "kind": "adj", "fg": 0, "emoji": "⬅️", "label": f"{'Botun Solu' if is_tr else 'Left of Bot'} ({max(0, bx - 1)}, {by})"},
        {"x": bx, "y": max(0, by - 1), "kind": "adj", "fg": 0, "emoji": "⬆️", "label": f"{'Botun Üstü' if is_tr else 'Above Bot'} ({bx}, {max(0, by - 1)})"},
        {"x": bx, "y": min(TILE_H - 1, by + 1), "kind": "adj", "fg": 0, "emoji": "⬇️", "label": f"{'Botun Altı' if is_tr else 'Below Bot'} ({bx}, {min(TILE_H - 1, by + 1)})"},
    ]
    seen_coords = {(lm["x"], lm["y"]) for lm in landmarks}

    parsed = _parse_tiles_arg(tiles)
    if parsed and len(parsed) >= TILE_W * TILE_H:
        specials = []
        trees = []
        for idx, fg in enumerate(parsed[: TILE_W * TILE_H]):
            if fg <= 0:
                continue
            tx = idx % TILE_W
            ty = idx // TILE_W
            if (tx, ty) in seen_coords:
                continue
            if fg in (6, 12):
                specials.append({"x": tx, "y": ty, "kind": "door", "fg": fg, "emoji": "🚪", "label": f"{'Ana Kapı' if is_tr else 'Main Door'} ({tx}, {ty})"})
            elif fg in LOCK_ITEM_IDS:
                specials.append({"x": tx, "y": ty, "kind": "lock", "fg": fg, "emoji": "🔒", "label": f"Lock [ID {fg}] ({tx}, {ty})"})
            elif fg in (26, 28):
                specials.append({"x": tx, "y": ty, "kind": "portal", "fg": fg, "emoji": "🌀", "label": f"{'Kapı/Portal' if is_tr else 'Door/Portal'} ({tx}, {ty})"})
            elif fg % 2 == 1 and fg > 15:
                trees.append({"x": tx, "y": ty, "kind": "tree", "fg": fg, "emoji": "🌱", "label": f"{'Ağaç/Tohum' if is_tr else 'Tree/Seed'} ({tx}, {ty})"})
        for item in specials[:10]:
            if (item["x"], item["y"]) not in seen_coords and len(landmarks) < max_items:
                landmarks.append(item)
                seen_coords.add((item["x"], item["y"]))
        for item in trees[:5]:
            if (item["x"], item["y"]) not in seen_coords and len(landmarks) < max_items:
                landmarks.append(item)
                seen_coords.add((item["x"], item["y"]))

    if other_players:
        for op in other_players:
            if len(landmarks) >= max_items:
                break
            if isinstance(op, dict):
                ox, oy = op.get("x", 0), op.get("y", 0)
                pname = str(op.get("name", "Player") or "Player")
            elif isinstance(op, (list, tuple)) and len(op) >= 2:
                ox, oy = op[0], op[1]
                pname = "Player"
            else:
                continue
            try:
                ox_i = int(ox)
                oy_i = int(oy)
            except (ValueError, TypeError):
                continue
            if ox_i >= 100:
                ox_i //= 32
            if oy_i >= 60:
                oy_i //= 32
            ox_i = max(0, min(TILE_W - 1, ox_i))
            oy_i = max(0, min(TILE_H - 1, oy_i))
            if (ox_i, oy_i) not in seen_coords:
                landmarks.append({"x": ox_i, "y": oy_i, "kind": "player", "fg": 0, "emoji": "👤", "label": f"{'Oyuncu' if is_tr else 'Player'} {pname[:18]} ({ox_i}, {oy_i})"})
                seen_coords.add((ox_i, oy_i))

    return landmarks[:max_items]


def render_minimap(
    tiles: Optional[Union[List[int], Dict[str, int], str]] = None,
    bot_x: int = 70,
    bot_y: int = 23,
    world_name: str = "ASDASDASDASVASD",
    is_public: bool = True,
    other_players: Optional[List[Any]] = None,
    target_pos: Optional[Tuple[int, int]] = None,
    lang: str = "en",
) -> Image.Image:
    """
    Renders an authentic, 1:1 replica of Lucifer Multibot's native [Map] tab window.
    Takes 100x60 tile foregrounds (list of 6000 ints, RLE string, or None to generate default GT world layout).
    Safely normalizes both pixel coordinates (e.g. 2240, 736) and tile coordinates (e.g. 70, 23).
    Optionally renders a yellow target crosshair at `target_pos=(tx, ty)`.
    """
    is_tr = str(lang or "en").lower().startswith("tr")
    try:
        bot_x = int(bot_x)
        bot_y = int(bot_y)
    except (ValueError, TypeError):
        bot_x, bot_y = 70, 23

    if bot_x >= 100:
        bot_x = bot_x // 32
    if bot_y >= 60:
        bot_y = bot_y // 32
    bot_x = max(0, min(TILE_W - 1, bot_x))
    bot_y = max(0, min(TILE_H - 1, bot_y))

    if isinstance(tiles, str):
        tiles = _parse_tiles_arg(tiles)

    # 1. Create base image
    img = Image.new("RGB", (IMG_W, IMG_H), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # 2. Draw Top Navigation Header Bar ([Growscan] [Map] [Players] [NPCs] [Dialog])
    draw.rectangle([0, 0, IMG_W, 26], fill=COLOR_HEADER_BG)
    draw.rectangle([108, 0, 216, 26], fill=COLOR_ACTIVE_TAB)  # [Map] tab highlight

    try:
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
        font_tab = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
    except Exception:
        font_small = ImageFont.load_default()
        font_tab = font_small

    draw.text((15, 6), "Growscan", fill=COLOR_TEXT_DIM, font=font_tab)
    draw.text((140, 6), "Map", fill=(255, 255, 255), font=font_tab)
    draw.text((245, 6), "Players", fill=COLOR_TEXT_DIM, font=font_tab)
    draw.text((355, 6), "NPCs", fill=COLOR_TEXT_DIM, font=font_tab)
    draw.text((455, 6), "Dialog", fill=COLOR_TEXT_DIM, font=font_tab)

    # 3. Draw Sub-Header Toggles (Fossil | Lock | Local | Player | Viewport)
    toggle_y = 36
    draw.text((8, toggle_y), "Fossil", fill=COLOR_TEXT_DIM, font=font_small)
    draw.rectangle([68, toggle_y + 2, 94, toggle_y + 12], fill=(20, 40, 60), outline=(80, 100, 130))

    draw.text((108, toggle_y), "|  Lock", fill=COLOR_TEXT_DIM, font=font_small)
    draw.rectangle([174, toggle_y + 2, 200, toggle_y + 12], fill=COLOR_TOGGLE_ON)
    draw.ellipse([188, toggle_y + 1, 199, toggle_y + 13], fill=(255, 255, 255))

    draw.text((214, toggle_y), "|  Local", fill=(255, 255, 255), font=font_small)
    draw.rectangle([282, toggle_y + 2, 308, toggle_y + 12], fill=COLOR_TOGGLE_ON)
    draw.ellipse([296, toggle_y + 1, 307, toggle_y + 13], fill=(255, 255, 255))

    draw.text((322, toggle_y), "|  Player", fill=COLOR_TEXT_DIM, font=font_small)
    draw.rectangle([390, toggle_y + 2, 416, toggle_y + 12], fill=(20, 40, 60), outline=(80, 100, 130))

    draw.text((430, toggle_y), "|  Viewport", fill=COLOR_TEXT_DIM, font=font_small)
    draw.rectangle([514, toggle_y + 2, 538, toggle_y + 12], fill=(20, 40, 60), outline=(80, 100, 130))

    # 4. Draw 100x60 Map Grid (Main Canvas)
    has_live_tiles = bool(tiles and len(tiles) >= (TILE_W * TILE_H))
    has_lock_tile = False
    if not has_live_tiles:
        import random
        rng = random.Random(hash(world_name))
        tiles_grid = [[0 for _ in range(TILE_W)] for _ in range(TILE_H)]
        for y in range(TILE_H):
            for x in range(TILE_W):
                if y < 24:
                    tiles_grid[y][x] = 0
                elif y < 54:
                    tiles_grid[y][x] = 10 if rng.random() < 0.07 else 2
                elif y < 58:
                    tiles_grid[y][x] = 4 if rng.random() < 0.65 else 10
                else:
                    tiles_grid[y][x] = 8
    else:
        tiles_grid = [[0 for _ in range(TILE_W)] for _ in range(TILE_H)]
        for idx, fg in enumerate(tiles[: TILE_W * TILE_H]):
            y = idx // TILE_W
            x = idx % TILE_W
            if isinstance(fg, dict):
                fg = fg.get("fg", 0)
            fg_val = int(fg) if isinstance(fg, (int, float)) else 0
            tiles_grid[y][x] = fg_val
            if fg_val in LOCK_ITEM_IDS:
                has_lock_tile = True

    effective_public = bool(is_public) and not has_lock_tile

    # Render each 5x5 tile + 1px dark contour on air boundaries (authentic Lucifer look)
    for y in range(TILE_H):
        row = tiles_grid[y]
        for x in range(TILE_W):
            fg = row[x]
            col = get_tile_color(fg)
            px = MAP_OFFSET_X + (x * TILE_PIXEL_SIZE)
            py = MAP_OFFSET_Y + (y * TILE_PIXEL_SIZE)
            px2 = px + TILE_PIXEL_SIZE - 1
            py2 = py + TILE_PIXEL_SIZE - 1
            draw.rectangle([px, py, px2, py2], fill=col)
            if fg > 0 and fg != 14:
                if y > 0 and tiles_grid[y - 1][x] in (0, 14):
                    draw.line([(px, py), (px2, py)], fill=COLOR_CONTOUR)
                if y < TILE_H - 1 and tiles_grid[y + 1][x] in (0, 14):
                    draw.line([(px, py2), (px2, py2)], fill=COLOR_CONTOUR)
                if x > 0 and row[x - 1] in (0, 14):
                    draw.line([(px, py), (px, py2)], fill=COLOR_CONTOUR)
                if x < TILE_W - 1 and row[x + 1] in (0, 14):
                    draw.line([(px2, py), (px2, py2)], fill=COLOR_CONTOUR)

    # 5. Draw Other Players (if any)
    if other_players:
        for op in other_players:
            if isinstance(op, (list, tuple)) and len(op) >= 2:
                ox, oy = op[0], op[1]
            elif isinstance(op, dict):
                ox, oy = op.get("x", 0), op.get("y", 0)
            else:
                continue
            try:
                ox = int(ox)
                oy = int(oy)
            except (ValueError, TypeError):
                continue
            if ox >= 100:
                ox = ox // 32
            if oy >= 60:
                oy = oy // 32
            ox = max(0, min(TILE_W - 1, ox))
            oy = max(0, min(TILE_H - 1, oy))
            opx = MAP_OFFSET_X + (ox * TILE_PIXEL_SIZE)
            opy = MAP_OFFSET_Y + (oy * TILE_PIXEL_SIZE)
            draw.rectangle([opx, opy, opx + TILE_PIXEL_SIZE - 1, opy + TILE_PIXEL_SIZE - 1], fill=COLOR_OTHER_PLAYER)

    # 6. Subtle exterior coordinate ticks (outside the cyan sky canvas so nothing overlaps)
    for gx in (0, 20, 40, 60, 80):
        ax_x = MAP_OFFSET_X + (gx * TILE_PIXEL_SIZE)
        draw.line([(ax_x, MAP_OFFSET_Y - 3), (ax_x, MAP_OFFSET_Y - 1)], fill=(120, 150, 185))
    for gy in (0, 15, 30, 45):
        ax_y = MAP_OFFSET_Y + (gy * TILE_PIXEL_SIZE)
        draw.line([(MAP_OFFSET_X - 4, ax_y), (MAP_OFFSET_X - 1, ax_y)], fill=(120, 150, 185))
        draw.text((2, ax_y - 4), str(gy), fill=(130, 155, 185), font=font_small)

    # 7. Draw Local Bot Marker (Bright Red square at bot_x, bot_y - identical to Lucifer native Map tab)
    bpx = MAP_OFFSET_X + (bot_x * TILE_PIXEL_SIZE)
    bpy = MAP_OFFSET_Y + (bot_y * TILE_PIXEL_SIZE)
    draw.rectangle([bpx - 1, bpy - 2, bpx + TILE_PIXEL_SIZE, bpy + TILE_PIXEL_SIZE - 1], fill=COLOR_BOT_MARKER)

    # 8. Optional Target Crosshair Marker (selected tile for Discord/Web interactive action)
    if target_pos is not None:
        try:
            tx = max(0, min(TILE_W - 1, int(target_pos[0])))
            ty = max(0, min(TILE_H - 1, int(target_pos[1])))
            tpx = MAP_OFFSET_X + (tx * TILE_PIXEL_SIZE) + (TILE_PIXEL_SIZE // 2)
            tpy = MAP_OFFSET_Y + (ty * TILE_PIXEL_SIZE) + (TILE_PIXEL_SIZE // 2)
            draw.rectangle([tpx - 5, tpy - 5, tpx + 5, tpy + 5], outline=(255, 230, 60), width=1)
            draw.line([(tpx - 9, tpy), (tpx + 9, tpy)], fill=(0, 240, 255), width=1)
            draw.line([(tpx, tpy - 9), (tpx, tpy + 9)], fill=(0, 240, 255), width=1)
            lbl = f"({tx},{ty})"
            lx = min(IMG_W - 56, max(MAP_OFFSET_X + 2, tpx + 8))
            ly = max(MAP_OFFSET_Y + 2, tpy - 14)
            draw.rectangle([lx - 2, ly - 1, lx + 48, ly + 11], fill=(10, 18, 34), outline=(255, 230, 60))
            draw.text((lx, ly), lbl, fill=(255, 240, 120), font=font_small)
        except Exception:
            pass

    # 9. Draw Bottom World Name Footer Bar ("WORLD_NAME [PUBLIC/PRIVATE]")
    footer_text = f"{world_name.upper()} [{'PUBLIC' if effective_public else 'PRIVATE'}]"
    if target_pos is not None:
        target_lbl = "HEDEF" if is_tr else "TARGET"
        footer_text += f" | {target_lbl}: ({target_pos[0]}, {target_pos[1]})"
    text_bbox = draw.textbbox((0, 0), footer_text, font=font_small)
    text_w = text_bbox[2] - text_bbox[0]
    center_x = (IMG_W - text_w) // 2
    draw.text((center_x, 368), footer_text, fill=(180, 195, 215), font=font_small)

    return img


def render_minimap_bytes(
    tiles: Optional[Union[List[int], Dict[str, int], str]] = None,
    bot_x: int = 70,
    bot_y: int = 23,
    world_name: str = "ASDASDASDASVASD",
    is_public: bool = True,
    other_players: Optional[List[Any]] = None,
    target_pos: Optional[Tuple[int, int]] = None,
    lang: str = "en",
) -> bytes:
    """Renders the minimap and returns PNG bytes for Discord or HTTP attachment."""
    img = render_minimap(
        tiles,
        bot_x,
        bot_y,
        world_name,
        is_public,
        other_players=other_players,
        target_pos=target_pos,
        lang=lang,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
