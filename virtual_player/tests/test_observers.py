"""Tests for Observer framework: ObserverBase, Aggregator, Exporter."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

from virtual_player.observers.base import ObserverBase, ScreenCaptureFn
from virtual_player.observers.aggregator import ParameterAggregator
from virtual_player.observers.exporter import DesignDBExporter, DomainGroup
from virtual_player.observers.generic_observers import (
    UIObserver, EconomyObserver, MonetizationObserver, ProgressionObserver,
)
from virtual_player.observers.puzzle_observers import BoardObserver, MatchObserver


# --- Test Observer Implementation ---

class DummyObserver(ObserverBase):
    def run(self):
        self.observe("test_param", 42, confidence=0.9, notes="test value")


# --- ObserverBase Tests ---

class TestObserverBase(unittest.TestCase):

    def test_observe_records(self):
        observations = {}
        obs = DummyObserver(1, "Test", "testing", lambda l: None, observations)
        obs.run()
        self.assertIn("test_param", observations)
        self.assertEqual(len(observations["test_param"]), 1)
        self.assertEqual(observations["test_param"][0]["value"], 42)
        self.assertEqual(observations["test_param"][0]["confidence"], 0.9)
        self.assertEqual(observations["test_param"][0]["observer"], 1)

    def test_observe_clips_confidence(self):
        observations = {}
        obs = DummyObserver(1, "Test", "testing", lambda l: None, observations)
        obs.observe("param", "val", confidence=1.5)
        self.assertEqual(observations["param"][0]["confidence"], 1.0)
        obs.observe("param", "val", confidence=-0.5)
        self.assertEqual(observations["param"][1]["confidence"], 0.0)

    def test_multiple_observations(self):
        observations = {}
        obs1 = DummyObserver(1, "Obs1", "dom1", lambda l: None, observations)
        obs2 = DummyObserver(2, "Obs2", "dom2", lambda l: None, observations)
        obs1.observe("shared_param", 10, confidence=0.8)
        obs2.observe("shared_param", 12, confidence=0.9)
        self.assertEqual(len(observations["shared_param"]), 2)

    def test_repr(self):
        obs = DummyObserver(5, "MyObs", "test", lambda l: None, {})
        self.assertIn("5", repr(obs))
        self.assertIn("MyObs", repr(obs))


# --- Aggregator Tests ---

class TestParameterAggregator(unittest.TestCase):

    def setUp(self):
        self.param_names = {
            "P01": "width",
            "P02": "height",
            "P03": "colors",
        }
        self.param_domains = {
            "P01": "ingame",
            "P02": "ingame",
            "P03": "ingame",
        }
        self.domain_weights = {
            1: {"ingame": 1.0},
            2: {"ingame": 0.8, "content": 1.0},
            3: {"ingame": 0.5},
        }
        self.agg = ParameterAggregator(
            param_names=self.param_names,
            param_domains=self.param_domains,
            domain_weights=self.domain_weights,
        )

    def test_single_observation(self):
        obs = {
            "P01": [{"value": 8, "confidence": 0.9, "observer": 1, "notes": "scan"}],
        }
        result = self.agg.aggregate(obs)
        self.assertEqual(result["P01"]["value"], 8)
        self.assertAlmostEqual(result["P01"]["confidence"], 0.9, places=2)

    def test_weighted_selection(self):
        """Higher domain-weighted observation should win."""
        obs = {
            "P01": [
                {"value": 8, "confidence": 0.9, "observer": 1, "notes": "observer1"},
                {"value": 10, "confidence": 0.9, "observer": 3, "notes": "observer3"},
            ],
        }
        result = self.agg.aggregate(obs)
        # Observer 1 has weight 1.0 for ingame, observer 3 has 0.5
        self.assertEqual(result["P01"]["value"], 8)

    def test_not_observed(self):
        obs = {}
        result = self.agg.aggregate(obs)
        self.assertEqual(result["P01"]["status"], "not_observed")
        self.assertIsNone(result["P01"]["value"])

    def test_top_3_sources(self):
        obs = {
            "P01": [
                {"value": 8, "confidence": 0.9, "observer": 1, "notes": "a"},
                {"value": 8, "confidence": 0.8, "observer": 2, "notes": "b"},
                {"value": 8, "confidence": 0.7, "observer": 3, "notes": "c"},
            ],
        }
        result = self.agg.aggregate(obs)
        self.assertLessEqual(len(result["P01"]["sources"]), 3)

    def test_skip_internal_keys(self):
        obs = {"_playthrough": [{"value": "internal"}]}
        result = self.agg.aggregate(obs)
        self.assertNotIn("_playthrough", result)

    def test_summary(self):
        obs = {
            "P01": [{"value": 8, "confidence": 0.9, "observer": 1, "notes": ""}],
        }
        result = self.agg.aggregate(obs)
        summary = self.agg.summary(result)
        self.assertIn("P01", summary)
        self.assertIn("width", summary)


# --- Exporter Tests ---

class TestDesignDBExporter(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_root = Path(self.tmpdir) / "design"

        self.groups = [
            DomainGroup(
                domain="ingame",
                design_id="test__ingame__mechanics",
                system="Game Mechanics",
                balance_area="core_mechanic",
                params=["P01", "P02"],
                provides=["board_layout"],
                tags=["puzzle"],
            ),
            DomainGroup(
                domain="bm",
                design_id="test__bm__monetization",
                system="Monetization",
                balance_area="monetization",
                params=["P03"],
                provides=["ad_system"],
                tags=["monetization"],
            ),
        ]

        self.exporter = DesignDBExporter(
            project="TestGame",
            genre="Puzzle",
            package_name="com.test.game",
            domain_groups=self.groups,
            db_root=self.db_root,
        )

    def test_export_creates_files(self):
        aggregated = {
            "P01": {"name": "width", "value": 8, "confidence": 0.9, "status": "observed"},
            "P02": {"name": "height", "value": 12, "confidence": 0.7, "status": "observed"},
            "P03": {"name": "ad_freq", "value": 0.5, "confidence": 0.6, "status": "observed"},
        }
        written = self.exporter.export(aggregated)
        self.assertGreater(len(written), 0)

        # Check ingame detail file
        ingame_file = self.db_root / "base" / "puzzle" / "ingame" / "files" / "test__ingame__mechanics.json"
        self.assertTrue(ingame_file.exists())
        data = json.loads(ingame_file.read_text(encoding="utf-8"))
        self.assertEqual(data["designId"], "test__ingame__mechanics")
        self.assertEqual(data["project"], "TestGame")
        self.assertEqual(data["genre"], "Puzzle")
        self.assertEqual(data["source"], "observed")
        self.assertEqual(data["score"], 0.4)
        self.assertIn("P01", data["content"]["parameters"])

    def test_export_creates_index(self):
        aggregated = {
            "P01": {"name": "width", "value": 8, "confidence": 0.9},
        }
        self.exporter.export(aggregated)

        index_path = self.db_root / "base" / "puzzle" / "ingame" / "index.json"
        self.assertTrue(index_path.exists())
        index = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(index), 1)
        self.assertEqual(index[0]["designId"], "test__ingame__mechanics")

    def test_export_upsert_index(self):
        """Re-export should update, not duplicate index entry."""
        aggregated = {
            "P01": {"name": "width", "value": 8, "confidence": 0.9},
        }
        self.exporter.export(aggregated)
        self.exporter.export(aggregated)

        index_path = self.db_root / "base" / "puzzle" / "ingame" / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        # Should have exactly 1 entry, not 2
        matching = [e for e in index if e["designId"] == "test__ingame__mechanics"]
        self.assertEqual(len(matching), 1)

    def test_dry_run(self):
        aggregated = {
            "P01": {"name": "width", "value": 8, "confidence": 0.9},
        }
        written = self.exporter.export(aggregated, dry_run=True)
        self.assertGreater(len(written), 0)
        # Files should NOT exist
        ingame_file = self.db_root / "base" / "puzzle" / "ingame" / "files" / "test__ingame__mechanics.json"
        self.assertFalse(ingame_file.exists())

    def test_domain_capitalization(self):
        aggregated = {
            "P03": {"name": "ad_freq", "value": 0.5, "confidence": 0.6},
        }
        self.exporter.export(aggregated)
        bm_file = self.db_root / "base" / "puzzle" / "bm" / "files" / "test__bm__monetization.json"
        self.assertTrue(bm_file.exists())
        data = json.loads(bm_file.read_text(encoding="utf-8"))
        self.assertEqual(data["domain"], "BM")

    def test_skip_empty_groups(self):
        aggregated = {}  # No params
        written = self.exporter.export(aggregated)
        self.assertEqual(len(written), 0)


# --- Generic Observer Tests ---

class TestGenericObservers(unittest.TestCase):

    def test_ui_observer(self):
        observations = {}
        obs = UIObserver(lambda l: None, observations)
        obs.run()
        self.assertIn("screen_resolution", observations)

    def test_economy_observer_currencies(self):
        observations = {}
        ocr_data = [("Gold: 1500", 0.9, 100, 200), ("Diamond: 50", 0.8, 100, 500)]
        obs = EconomyObserver(lambda l: Path("/dummy"), observations,
                              ocr_fn=lambda p: ocr_data)
        obs.run()
        self.assertIn("currency_types", observations)
        vals = observations["currency_types"][0]["value"]
        self.assertIn("gold", vals)

    def test_monetization_observer(self):
        observations = {}
        obs = MonetizationObserver(lambda l: None, observations)
        obs._levels_played = 5
        obs._ad_count = 2
        obs.run()
        self.assertIn("interstitial_ad_freq", observations)
        self.assertAlmostEqual(observations["interstitial_ad_freq"][0]["value"], 0.4)

    def test_progression_observer_difficulty(self):
        observations = {}
        obs = ProgressionObserver(lambda l: None, observations)
        obs._level_stats = [
            {"difficulty": 5}, {"difficulty": 6}, {"difficulty": 7},
            {"difficulty": 10}, {"difficulty": 12}, {"difficulty": 15},
        ]
        obs.run()
        self.assertIn("difficulty_curve_type", observations)
        self.assertEqual(observations["difficulty_curve_type"][0]["value"], "increasing")


# --- Puzzle Observer Tests ---

class TestPuzzleObservers(unittest.TestCase):

    def test_board_observer(self):
        observations = {}
        obs = BoardObserver(lambda l: None, observations)
        obs.record_board_state({
            "columns": 8, "rows": 12,
            "colors": ["red", "blue", "green", "red", "blue"],
            "stack_depths": [3, 5, 4, 6, 2],
        })
        obs.run()
        self.assertIn("board_width_cells", observations)
        self.assertEqual(observations["board_width_cells"][0]["value"], 8)
        self.assertIn("car_color_count", observations)
        self.assertEqual(observations["car_color_count"][0]["value"], 3)

    def test_match_observer_default(self):
        observations = {}
        obs = MatchObserver(lambda l: None, observations)
        obs.run()
        self.assertIn("match_threshold", observations)
        self.assertEqual(observations["match_threshold"][0]["value"], 3)

    def test_match_observer_events(self):
        observations = {}
        obs = MatchObserver(lambda l: None, observations)
        obs.record_match_event({"matched_count": 3, "holder_capacity": 7})
        obs.record_match_event({"matched_count": 3, "holder_capacity": 7})
        obs.run()
        self.assertEqual(observations["match_threshold"][0]["value"], 3)
        self.assertIn("holder_capacity", observations)


if __name__ == "__main__":
    unittest.main()
