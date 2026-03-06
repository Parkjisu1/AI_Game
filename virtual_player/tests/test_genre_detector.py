"""Tests for GenreDetector."""

import unittest

from virtual_player.bootstrap.genre_detector import GenreDetector


class TestGenreDetector(unittest.TestCase):

    def setUp(self):
        self.detector = GenreDetector()

    def _make_discovery(self, screens, transitions=None):
        data = {"screens": {}, "transitions": transitions or []}
        for name in screens:
            data["screens"][name] = {
                "visit_count": 1, "elements": [], "tags": [],
            }
        return data

    def test_detect_rpg(self):
        discovery = self._make_discovery(
            ["lobby", "battle", "town", "map", "inventory", "quest"])
        ocr_texts = ["HP: 500", "MP: 200", "Level 32", "Quest", "스킬"]
        genre, scores = self.detector.detect(discovery, ocr_texts)
        self.assertEqual(genre, "rpg")
        self.assertGreater(scores["rpg"], scores["puzzle"])

    def test_detect_idle(self):
        discovery = self._make_discovery(["main", "shop", "upgrade"])
        ocr_texts = ["idle income", "offline reward", "/s", "prestige", "방치"]
        genre, scores = self.detector.detect(discovery, ocr_texts)
        self.assertEqual(genre, "idle")

    def test_detect_puzzle(self):
        discovery = self._make_discovery(["lobby", "gameplay", "win"])
        ocr_texts = ["Score: 1500", "Level 87", "Lives: 5", "매치", "콤보"]
        genre, scores = self.detector.detect(discovery, ocr_texts)
        self.assertEqual(genre, "puzzle")

    def test_detect_merge(self):
        discovery = self._make_discovery(["garden", "board", "orders"])
        ocr_texts = ["merge items", "drag and drop", "combine", "주문", "에너지"]
        genre, scores = self.detector.detect(discovery, ocr_texts)
        self.assertEqual(genre, "merge")

    def test_detect_slg(self):
        discovery = self._make_discovery(
            ["world_map", "city", "barracks", "alliance", "research", "hero"])
        ocr_texts = ["Alliance", "Troops", "March", "Kingdom", "Scout"]
        transitions = [{"from_screen": s, "to_screen": t, "via": []}
                       for s, t in [("world_map", "city"), ("city", "barracks"),
                                    ("city", "alliance"), ("world_map", "hero"),
                                    ("city", "research"), ("alliance", "war"),
                                    ("barracks", "troops"), ("troops", "march"),
                                    ("hero", "skills"), ("research", "tech")]]
        discovery["transitions"] = transitions
        genre, scores = self.detector.detect(discovery, ocr_texts)
        self.assertEqual(genre, "slg")

    def test_empty_input(self):
        discovery = self._make_discovery([])
        genre, scores = self.detector.detect(discovery)
        self.assertIsInstance(genre, str)
        self.assertIsInstance(scores, dict)

    def test_element_text_matching(self):
        """OCR text in elements should contribute to scoring."""
        discovery = {
            "screens": {
                "main": {
                    "visit_count": 1,
                    "elements": [
                        {"label": "quest_button", "ocr_text": "퀘스트", "x": 100, "y": 200},
                        {"label": "skill_icon", "ocr_text": "스킬", "x": 300, "y": 400},
                    ],
                    "tags": [],
                },
            },
            "transitions": [],
        }
        genre, scores = self.detector.detect(discovery)
        self.assertGreater(scores["rpg"], 0)


if __name__ == "__main__":
    unittest.main()
