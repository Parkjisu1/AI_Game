"""Tests for DiscoveryDB."""

import json
import tempfile
import unittest
from pathlib import Path

from virtual_player.discovery.discovery_db import DiscoveryDB


class TestDiscoveryDBInMemory(unittest.TestCase):
    """Tests for DiscoveryDB without file persistence."""

    def setUp(self):
        self.db = DiscoveryDB()

    def test_empty_init(self):
        self.assertEqual(self.db.screens, {})
        self.assertEqual(self.db.transitions, [])
        self.assertEqual(self.db.failed_taps, [])

    def test_record_element_new_screen(self):
        self.db.record_element("lobby", 100, 200, "Play", "gameplay", True)
        self.assertIn("lobby", self.db.screens)
        elems = self.db.screens["lobby"]["elements"]
        self.assertEqual(len(elems), 1)
        self.assertEqual(elems[0]["x"], 100)
        self.assertEqual(elems[0]["y"], 200)
        self.assertEqual(elems[0]["ocr_text"], "Play")
        self.assertEqual(elems[0]["target_screen"], "gameplay")
        self.assertEqual(elems[0]["tap_count"], 1)
        self.assertEqual(elems[0]["success_count"], 1)

    def test_record_element_deduplication(self):
        """Elements within COORD_TOLERANCE should merge."""
        self.db.record_element("lobby", 100, 200, "Play", "gameplay", True)
        # Tap nearby (within tolerance=50)
        self.db.record_element("lobby", 120, 210, "", "", True)
        elems = self.db.screens["lobby"]["elements"]
        self.assertEqual(len(elems), 1)
        self.assertEqual(elems[0]["tap_count"], 2)
        self.assertEqual(elems[0]["success_count"], 2)

    def test_record_element_far_apart(self):
        """Elements beyond COORD_TOLERANCE should be separate."""
        self.db.record_element("lobby", 100, 200, "Play", "gameplay", True)
        self.db.record_element("lobby", 500, 800, "Shop", "shop", True)
        elems = self.db.screens["lobby"]["elements"]
        self.assertEqual(len(elems), 2)

    def test_record_element_tags(self):
        self.db.record_element("lobby", 100, 200, "Play", "", True, tags=["button", "primary"])
        elems = self.db.screens["lobby"]["elements"]
        self.assertIn("button", elems[0]["tags"])
        self.assertIn("primary", elems[0]["tags"])

    def test_record_transition(self):
        steps = [{"action": "tap", "x": 100, "y": 200}]
        self.db.record_transition("lobby", "gameplay", steps)
        self.assertEqual(len(self.db.transitions), 1)
        self.assertEqual(self.db.transitions[0]["from_screen"], "lobby")
        self.assertEqual(self.db.transitions[0]["to_screen"], "gameplay")
        self.assertEqual(self.db.transitions[0]["success_count"], 1)

    def test_record_transition_increment(self):
        steps = [{"action": "tap", "x": 100, "y": 200}]
        self.db.record_transition("lobby", "gameplay", steps)
        self.db.record_transition("lobby", "gameplay", steps)
        self.assertEqual(len(self.db.transitions), 1)
        self.assertEqual(self.db.transitions[0]["success_count"], 2)

    def test_record_failure_and_dead_zone(self):
        self.db.record_failure("lobby", 500, 1850)
        self.assertFalse(self.db.is_dead_zone("lobby", 500, 1850))  # only 1 fail

        self.db.record_failure("lobby", 500, 1850)
        self.assertFalse(self.db.is_dead_zone("lobby", 500, 1850))  # 2 fails

        self.db.record_failure("lobby", 500, 1850)
        self.assertTrue(self.db.is_dead_zone("lobby", 500, 1850))   # 3 fails = dead

    def test_record_visit(self):
        self.db.record_visit("lobby")
        self.assertEqual(self.db.screens["lobby"]["visit_count"], 1)
        self.db.record_visit("lobby")
        self.assertEqual(self.db.screens["lobby"]["visit_count"], 2)

    def test_get_untapped_regions_empty(self):
        points = self.db.get_untapped_regions("unknown_screen")
        # 5 cols x 8 rows = 40 points
        self.assertEqual(len(points), 40)

    def test_get_untapped_regions_excludes_elements(self):
        # Add an element, the grid cell covering it should be excluded
        self.db.record_element("lobby", 108, 216, "Play", "", True)
        points = self.db.get_untapped_regions("lobby")
        self.assertLess(len(points), 40)

    def test_get_untapped_regions_excludes_dead_zones(self):
        # Mark a zone as dead
        for _ in range(3):
            self.db.record_failure("lobby", 108, 216)
        points = self.db.get_untapped_regions("lobby")
        self.assertLess(len(points), 40)

    def test_find_element(self):
        self.db.record_element("shop", 300, 400, "Gold Pack", "purchase", True)
        result = self.db.find_element("shop", "gold")
        self.assertEqual(result, (300, 400))

    def test_find_element_not_found(self):
        result = self.db.find_element("shop", "diamond")
        self.assertIsNone(result)

    def test_find_path_to_direct(self):
        """Direct element on a screen should return a single-step path."""
        self.db.record_element("lobby", 300, 400, "Settings", "settings", True)
        path = self.db.find_path_to("settings")
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 1)
        self.assertEqual(path[0]["x"], 300)

    def test_find_path_to_via_transition(self):
        """Element reachable via transition should include transition steps."""
        self.db.record_element("lobby", 100, 200, "Map", "map", True)
        self.db.record_element("map", 500, 600, "Battle Start", "battle", True)
        self.db.record_transition("lobby", "map",
                                  [{"action": "tap", "x": 100, "y": 200}])

        path = self.db.find_path_to("battle")
        self.assertIsNotNone(path)
        # Should include transition step + element tap
        self.assertGreaterEqual(len(path), 2)

    def test_find_path_to_not_found(self):
        path = self.db.find_path_to("nonexistent_element")
        self.assertIsNone(path)

    def test_get_screen_names(self):
        self.db.record_visit("lobby")
        self.db.record_visit("shop")
        names = self.db.get_screen_names()
        self.assertIn("lobby", names)
        self.assertIn("shop", names)

    def test_get_transitions_from(self):
        self.db.record_transition("lobby", "shop", [{"action": "tap", "x": 100, "y": 200}])
        self.db.record_transition("lobby", "battle", [{"action": "tap", "x": 300, "y": 400}])
        self.db.record_transition("shop", "lobby", [{"action": "tap", "x": 50, "y": 50}])

        from_lobby = self.db.get_transitions_from("lobby")
        self.assertEqual(len(from_lobby), 2)

    def test_to_dict(self):
        self.db.record_element("lobby", 100, 200, "Play", "", True)
        data = self.db.to_dict()
        self.assertIn("screens", data)
        self.assertIn("transitions", data)
        self.assertIn("failed_taps", data)

    def test_merge(self):
        db2 = DiscoveryDB()
        db2.record_element("shop", 200, 300, "Buy", "purchase", True)
        db2.record_transition("lobby", "shop", [{"action": "tap", "x": 200, "y": 300}])

        self.db.record_element("lobby", 100, 200, "Shop", "shop", True)
        self.db.merge(db2)

        self.assertIn("shop", self.db.screens)
        self.assertIn("lobby", self.db.screens)
        self.assertEqual(len(self.db.transitions), 1)


class TestDiscoveryDBPersistence(unittest.TestCase):
    """Tests for DiscoveryDB file save/load."""

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_db.json"

            # Create and save
            db1 = DiscoveryDB(db_path=db_path)
            db1.record_element("lobby", 100, 200, "Play", "gameplay", True)
            db1.record_transition("lobby", "gameplay",
                                  [{"action": "tap", "x": 100, "y": 200}])
            db1.record_failure("lobby", 500, 1850)
            db1.save()

            self.assertTrue(db_path.exists())

            # Load into new instance
            db2 = DiscoveryDB(db_path=db_path)
            self.assertIn("lobby", db2.screens)
            self.assertEqual(len(db2.screens["lobby"]["elements"]), 1)
            self.assertEqual(len(db2.transitions), 1)
            self.assertEqual(len(db2.failed_taps), 1)

    def test_save_no_path(self):
        """save() with no db_path should be a no-op."""
        db = DiscoveryDB()
        db.record_element("lobby", 100, 200, "Play", "", True)
        db.save()  # Should not raise

    def test_seed_data(self):
        seed = {
            "screens": {
                "hub": {"visit_count": 5, "elements": [
                    {"x": 100, "y": 200, "label": "start", "ocr_text": "Start",
                     "target_screen": "game", "tap_count": 5, "success_count": 5,
                     "tags": [], "source": "seed"}
                ], "tags": ["main"]},
            },
            "transitions": [],
            "failed_taps": [],
        }
        db = DiscoveryDB(seed_data=seed)
        self.assertIn("hub", db.screens)
        self.assertEqual(len(db.screens["hub"]["elements"]), 1)

    def test_load_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "corrupt.json"
            db_path.write_text("NOT VALID JSON!!!", encoding="utf-8")

            db = DiscoveryDB(db_path=db_path)
            self.assertEqual(db.screens, {})

    def test_max_elements_trim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "trim.json"
            db = DiscoveryDB(db_path=db_path)

            # Add more than MAX_ELEMENTS
            for i in range(60):
                db.screens.setdefault("test", {"visit_count": 0, "elements": [], "tags": []})
                db.screens["test"]["elements"].append({
                    "x": i * 20, "y": 100,
                    "label": f"elem_{i}", "ocr_text": "", "target_screen": "",
                    "tap_count": i, "success_count": 0, "tags": [], "source": "test",
                })

            db.save()

            db2 = DiscoveryDB(db_path=db_path)
            self.assertLessEqual(len(db2.screens["test"]["elements"]), DiscoveryDB.MAX_ELEMENTS)


if __name__ == "__main__":
    unittest.main()
