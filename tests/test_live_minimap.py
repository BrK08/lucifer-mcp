import io
import unittest
from PIL import Image

from core.bot_manager import BotManager, BotState
from core.minimap_renderer import (
    render_minimap,
    render_minimap_bytes,
    get_tile_color,
    COLOR_BOT_MARKER,
    COLOR_OTHER_PLAYER,
    COLOR_GOLD_LOCK,
    COLOR_TREE,
    TILE_W,
    TILE_H,
)


class TestLiveMinimap(unittest.TestCase):
    def test_coordinate_normalization(self):
        # Raw Growtopia pixel coords (e.g. 2240, 736) should be converted to tile (70, 23)
        img = render_minimap(bot_x=2240, bot_y=736, world_name="TESTWORLD")
        self.assertIsInstance(img, Image.Image)
        self.assertEqual(img.size, (544, 389))

        # Check out-of-bounds coordinates clamped
        img_oob = render_minimap(bot_x=-50, bot_y=9999)
        self.assertIsInstance(img_oob, Image.Image)

    def test_rle_tile_parsing(self):
        # RLE format: "2:100,4:50,8:200"
        rle_str = "2:100,4:50,8:200"
        img_bytes = render_minimap_bytes(tiles=rle_str, bot_x=10, bot_y=10)
        self.assertTrue(len(img_bytes) > 0)
        self.assertTrue(img_bytes.startswith(b"\x89PNG"))

    def test_other_players_rendering(self):
        players = [
            {"name": "Player1", "x": 1600, "y": 640},  # Pixel coords (50, 20)
            {"name": "Player2", "x": 30, "y": 15},     # Tile coords (30, 15)
            (40, 25),                                  # Tuple format
        ]
        img = render_minimap(
            bot_x=10,
            bot_y=10,
            world_name="PEOPLEWORLD",
            other_players=players,
        )
        self.assertIsInstance(img, Image.Image)

    def test_bot_state_properties(self):
        state = BotState(name="TestBot", x=2240, y=736)
        self.assertEqual(state.tile_x, 70)
        self.assertEqual(state.tile_y, 23)

        state2 = BotState(name="TestBot2", x=45, y=20)
        self.assertEqual(state2.tile_x, 45)
        self.assertEqual(state2.tile_y, 20)

    def test_bot_manager_heartbeat_rle_tiles(self):
        manager = BotManager()
        payload = {
            "name": "RadarBot",
            "world": "FARMWORLD",
            "x": 1600,
            "y": 640,
            "tiles_rle": "0:2400,2:100,4584:50",
            "players": [{"name": "Visitor", "x": 50, "y": 20}],
        }
        bot = manager.update_heartbeat(payload)
        self.assertEqual(bot.name, "RadarBot")
        self.assertEqual(bot.world, "FARMWORLD")
        self.assertEqual(bot.tile_x, 50)
        self.assertEqual(bot.tile_y, 20)
        self.assertEqual(len(bot.tiles), 2550)
        self.assertEqual(bot.tiles[0], 0)
        self.assertEqual(bot.tiles[2400], 2)
        self.assertEqual(bot.tiles[2500], 4584)
        self.assertEqual(len(bot.other_players), 1)

    def test_tile_colors(self):
        self.assertEqual(get_tile_color(242), COLOR_GOLD_LOCK)
        self.assertEqual(get_tile_color(7188), COLOR_GOLD_LOCK)
        self.assertEqual(get_tile_color(4584), COLOR_TREE)
        self.assertEqual(get_tile_color(4570), COLOR_TREE)


if __name__ == "__main__":
    unittest.main()
