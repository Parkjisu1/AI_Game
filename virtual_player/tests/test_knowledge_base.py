"""Tests for KnowledgeBase and TransferEngine."""

import json
import tempfile
import unittest
from pathlib import Path

from virtual_player.knowledge.knowledge_base import KnowledgeBase
from virtual_player.knowledge.screen_archetypes import ScreenArchetypes
from virtual_player.knowledge.transfer_engine import TransferEngine


class TestKnowledgeBase(unittest.TestCase):

    def test_in_memory(self):
        kb = KnowledgeBase()
        kb.register_game("com.test.game", "rpg", "TestRPG")
        self.assertTrue(kb.has_game("com.test.game"))
        game = kb.get_game("com.test.game")
        self.assertEqual(game["genre"], "rpg")

    def test_register_and_session(self):
        kb = KnowledgeBase()
        kb.register_game("com.test.game", "rpg")
        kb.record_session("com.test.game", {
            "screen_types": {"lobby": "Main menu", "battle": "Combat"},
            "parameters": {"hp_max": 500},
            "learned_actions": ["tap_attack"],
        })
        game = kb.get_game("com.test.game")
        self.assertEqual(game["sessions"], 1)
        self.assertIn("lobby", game["screen_types"])
        self.assertEqual(game["parameters"]["hp_max"], 500)

    def test_get_games_by_genre(self):
        kb = KnowledgeBase()
        kb.register_game("com.rpg1", "rpg")
        kb.register_game("com.rpg2", "rpg")
        kb.register_game("com.puzzle1", "puzzle")
        rpgs = kb.get_games_by_genre("rpg")
        self.assertEqual(len(rpgs), 2)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "kb.json"
            kb1 = KnowledgeBase(db_path=db_path)
            kb1.register_game("com.test", "rpg")
            kb1.save()

            kb2 = KnowledgeBase(db_path=db_path)
            self.assertTrue(kb2.has_game("com.test"))

    def test_auto_register_on_session(self):
        kb = KnowledgeBase()
        kb.record_session("com.new.game", {"screen_types": {}})
        self.assertTrue(kb.has_game("com.new.game"))


class TestScreenArchetypes(unittest.TestCase):

    def test_match_lobby(self):
        arch = ScreenArchetypes()
        matches = arch.match(["Play", "Start", "Settings"])
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0][0], "lobby")

    def test_match_shop(self):
        arch = ScreenArchetypes()
        matches = arch.match(["Shop", "Buy", "Purchase"])
        names = [m[0] for m in matches]
        self.assertIn("shop", names)

    def test_is_safe(self):
        arch = ScreenArchetypes()
        self.assertTrue(arch.is_safe("lobby"))
        self.assertFalse(arch.is_safe("shop"))
        self.assertTrue(arch.is_safe("unknown_screen"))

    def test_get_keywords(self):
        arch = ScreenArchetypes()
        kw = arch.get_keywords("battle")
        self.assertIn("hp", kw)


class TestTransferEngine(unittest.TestCase):

    def test_no_prior_games(self):
        kb = KnowledgeBase()
        te = TransferEngine(kb)
        result = te.get_transfer_data("com.new.game", "rpg")
        self.assertIsNone(result)

    def test_transfer_from_same_genre(self):
        kb = KnowledgeBase()
        kb.register_game("com.rpg1", "rpg")
        kb.record_session("com.rpg1", {
            "screen_types": {"lobby": "Main", "battle": "Fight"},
            "parameters": {"hp_max": 500},
        })

        te = TransferEngine(kb)
        result = te.get_transfer_data("com.rpg2", "rpg")
        self.assertIsNotNone(result)
        self.assertIn("lobby", result["screen_types"])
        self.assertEqual(result["common_parameters"]["hp_max"], 500)

    def test_apply_transfer(self):
        kb = KnowledgeBase()
        kb.register_game("com.rpg1", "rpg")
        kb.record_session("com.rpg1", {
            "screen_types": {"shop": "Item shop"},
        })

        te = TransferEngine(kb)
        transfer = te.get_transfer_data("com.rpg2", "rpg")

        discovery = {"screens": {"lobby": {"visit_count": 1, "elements": [], "tags": []}}}
        enriched = te.apply_transfer(transfer, discovery)

        self.assertIn("shop", enriched["screens"])
        self.assertTrue(enriched.get("_transfer_applied"))


if __name__ == "__main__":
    unittest.main()
