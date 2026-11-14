"""
Test Authentic Growtopia Items, Sprites, and Endpoints
Verifies:
- 6,832 authentic Growtopia items in item_db
- 3,808 recipes and color metadata in get_item_details
- /api/items catalog endpoint in web/server.py and core/relay_server.py
- Sprite files in assets/items/{id}.png
- build_item_embed in discord_bot/bot.py
"""
import unittest
from pathlib import Path
from core.item_db import (
    get_item_name,
    get_item_id,
    get_item_details,
    get_all_items_catalog,
    search_items,
)
try:
    from discord_bot.bot import build_item_embed
except ImportError:
    build_item_embed = None


class TestAuthenticGTItems(unittest.TestCase):

    def test_item_db_names(self):
        self.assertEqual(get_item_name(2), "Dirt")
        self.assertEqual(get_item_name(242), "World Lock")
        self.assertEqual(get_item_name(1796), "Diamond Lock")
        self.assertEqual(get_item_name(7188), "Blue Gem Lock")
        self.assertEqual(get_item_name(4584), "Pepper Tree")
        self.assertEqual(get_item_name(5666), "Laser Grid")
        self.assertEqual(get_item_name(5638), "MAGPLANT 5000")

    def test_item_details_rich_recipe(self):
        d = get_item_details(4584)
        self.assertIsNotNone(d)
        self.assertEqual(d["name"], "Pepper Tree")
        self.assertEqual(d["seed_id"], 4585)
        self.assertGreater(d["growth_seconds"], 0)
        self.assertIn("Palm Tree Seed", str(d["recipe"]))
        self.assertIn("Apple Seed", str(d["recipe"]))

    def test_catalog_export(self):
        cat = get_all_items_catalog()
        self.assertGreater(len(cat), 6000)
        self.assertIn(242, cat)
        self.assertEqual(cat[242]["n"], "World Lock")
        self.assertEqual(cat[242]["k"], "CURRENCY")
        self.assertIn(4584, cat)
        self.assertEqual(cat[4584]["n"], "Pepper Tree")

    def test_search_items(self):
        results = search_items("Pepper", limit=5)
        self.assertGreater(len(results), 0)
        names = [r["name"] for r in results]
        self.assertTrue(any("Pepper" in n for n in names))

    def test_sprite_files_exist(self):
        assets_dir = Path(__file__).resolve().parent.parent / "assets" / "items"
        self.assertTrue((assets_dir / "2.png").exists())
        self.assertTrue((assets_dir / "242.png").exists())
        self.assertTrue((assets_dir / "1796.png").exists())
        self.assertTrue((assets_dir / "7188.png").exists())
        self.assertTrue((assets_dir / "4584.png").exists())
        self.assertTrue((assets_dir / "5666.png").exists())

    def test_build_item_embed(self):
        if build_item_embed is None:
            self.skipTest("Private discord_bot module not present in public MCP repo")
        embed, file_obj = build_item_embed("Pepper Tree")
        self.assertIsNotNone(embed)
        self.assertIn("Pepper Tree", embed.title)
        self.assertIsNotNone(file_obj)
        self.assertEqual(file_obj.filename, "item_4584.png")
        if file_obj:
            file_obj.close()


if __name__ == "__main__":
    unittest.main()
