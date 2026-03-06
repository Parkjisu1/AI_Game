"""Tests for learning package -- PatternDB, PatternRecorder, PatternExecutor."""

import json
import tempfile
import unittest
from pathlib import Path

from virtual_player.learning.action_pattern import ActionStep, ActionPattern, PatternDB
from virtual_player.learning.pattern_executor import PatternExecutor


class TestActionStep(unittest.TestCase):
    """Test ActionStep dataclass."""

    def test_default_values(self):
        step = ActionStep(screen_type="lobby")
        self.assertEqual(step.screen_type, "lobby")
        self.assertEqual(step.intent, "")
        self.assertEqual(step.action_type, "tap")
        self.assertEqual(step.fallback_x, 540)
        self.assertEqual(step.fallback_y, 960)
        self.assertEqual(step.confidence, 1.0)

    def test_custom_step(self):
        step = ActionStep(
            screen_type="menu_shop",
            intent="confirm",
            target_text="확인",
            action_type="tap",
            fallback_x=500,
            fallback_y=800,
        )
        self.assertEqual(step.target_text, "확인")
        self.assertEqual(step.fallback_x, 500)


class TestActionPattern(unittest.TestCase):
    """Test ActionPattern dataclass."""

    def test_success_rate_zero(self):
        pattern = ActionPattern(name="test", category="quest")
        self.assertEqual(pattern.success_rate, 0.0)

    def test_success_rate_calculation(self):
        pattern = ActionPattern(name="test", category="quest",
                                use_count=10, success_count=7)
        self.assertAlmostEqual(pattern.success_rate, 0.7)

    def test_to_dict_and_from_dict(self):
        steps = [
            ActionStep(screen_type="lobby", intent="navigate", target_text="shop"),
            ActionStep(screen_type="menu_shop", intent="tap_button", target_text="buy"),
        ]
        pattern = ActionPattern(
            name="buy_potion",
            category="shop",
            description="Buy HP potion",
            trigger_screen="lobby",
            trigger_text=["shop"],
            steps=steps,
            use_count=5,
            success_count=3,
        )

        d = pattern.to_dict()
        self.assertEqual(d["name"], "buy_potion")
        self.assertEqual(len(d["steps"]), 2)

        # Round-trip
        restored = ActionPattern.from_dict(d)
        self.assertEqual(restored.name, "buy_potion")
        self.assertEqual(len(restored.steps), 2)
        self.assertEqual(restored.steps[0].target_text, "shop")
        self.assertEqual(restored.use_count, 5)


class TestPatternDB(unittest.TestCase):
    """Test PatternDB persistence and queries."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_save_and_load(self):
        db_path = self.tmpdir / "patterns.json"
        db = PatternDB(db_path)

        pattern = ActionPattern(
            name="quest_1", category="quest",
            trigger_screen="lobby", trigger_text=["quest"],
            steps=[ActionStep(screen_type="lobby", intent="navigate")],
        )
        db.add(pattern)
        self.assertEqual(db.count, 1)

        # Reload from disk
        db2 = PatternDB(db_path)
        self.assertEqual(db2.count, 1)
        loaded = db2.get("quest_1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.category, "quest")

    def test_get_by_category(self):
        db = PatternDB(self.tmpdir / "db.json")
        db.add(ActionPattern(name="q1", category="quest"))
        db.add(ActionPattern(name="q2", category="quest"))
        db.add(ActionPattern(name="p1", category="popup"))

        quests = db.get_by_category("quest")
        self.assertEqual(len(quests), 2)
        popups = db.get_by_category("popup")
        self.assertEqual(len(popups), 1)

    def test_get_by_trigger(self):
        db = PatternDB(self.tmpdir / "db.json")
        db.add(ActionPattern(
            name="shop_buy", category="shop",
            trigger_screen="menu_shop", trigger_text=["buy"],
        ))
        db.add(ActionPattern(
            name="quest_accept", category="quest",
            trigger_screen="lobby", trigger_text=["quest"],
        ))

        # Match by screen
        matches = db.get_by_trigger("menu_shop", ["buy this item"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].name, "shop_buy")

        # No match
        matches = db.get_by_trigger("battle", ["attack"])
        self.assertEqual(len(matches), 0)

    def test_get_by_trigger_sorted_by_success(self):
        db = PatternDB(self.tmpdir / "db.json")
        db.add(ActionPattern(
            name="p1", category="popup",
            trigger_screen="popup",
            use_count=10, success_count=3,
        ))
        db.add(ActionPattern(
            name="p2", category="popup",
            trigger_screen="popup",
            use_count=10, success_count=8,
        ))

        matches = db.get_by_trigger("popup")
        self.assertEqual(matches[0].name, "p2")  # Higher success rate

    def test_remove(self):
        db = PatternDB(self.tmpdir / "db.json")
        db.add(ActionPattern(name="x", category="quest"))
        self.assertTrue(db.remove("x"))
        self.assertEqual(db.count, 0)
        self.assertFalse(db.remove("nonexistent"))


class TestPatternExecutor(unittest.TestCase):
    """Test PatternExecutor matching and execution."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self.taps = []

        # Create a pattern DB with a sample pattern
        self.db = PatternDB(self.tmpdir / "db.json")
        self.db.add(ActionPattern(
            name="close_popup",
            category="popup",
            trigger_screen="popup_reward",
            steps=[
                ActionStep(
                    screen_type="popup_reward",
                    intent="collect_reward",
                    target_text="보상",
                    action_type="tap",
                    fallback_x=540, fallback_y=1200,
                    wait_after=1.0,
                ),
                ActionStep(
                    screen_type="popup_reward",
                    intent="close",
                    target_text="확인",
                    action_type="tap",
                    fallback_x=540, fallback_y=1400,
                    wait_after=1.0,
                ),
            ],
        ))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _tap(self, x, y, wait=0):
        self.taps.append((x, y))

    def _read_text(self, path):
        return []  # No OCR in tests

    def test_try_match(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        # Matching screen
        matched = executor.try_match("popup_reward")
        self.assertEqual(matched, "close_popup")

        # Non-matching screen
        matched = executor.try_match("battle")
        self.assertIsNone(matched)

    def test_start_pattern(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        self.assertFalse(executor.is_executing)

        result = executor.start_pattern("close_popup")
        self.assertTrue(result)
        self.assertTrue(executor.is_executing)
        self.assertEqual(executor.active_pattern_name, "close_popup")

    def test_start_nonexistent_pattern(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        result = executor.start_pattern("nonexistent")
        self.assertFalse(result)

    def test_execute_steps(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        executor.start_pattern("close_popup")

        # Execute step 1 (fallback coords since no OCR)
        result = executor.execute_step("popup_reward")
        self.assertIsNotNone(result)
        self.assertIn("collect_reward", result)
        self.assertEqual(len(self.taps), 1)
        self.assertEqual(self.taps[0], (540, 1200))

        # Execute step 2
        result = executor.execute_step("popup_reward")
        self.assertIsNotNone(result)
        self.assertIn("close", result)
        self.assertEqual(len(self.taps), 2)
        self.assertEqual(self.taps[1], (540, 1400))

        # Pattern should be complete
        self.assertFalse(executor.is_executing)

    def test_wrong_screen_retries(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        executor.start_pattern("close_popup")
        executor.MAX_RETRIES = 2

        # Wrong screen -- should not execute, just retry
        result = executor.execute_step("battle")
        self.assertIsNone(result)
        self.assertEqual(len(self.taps), 0)

        # Still executing (retry pending)
        self.assertTrue(executor.is_executing)

        # Exceed retries -> pattern aborted
        executor.execute_step("battle")
        executor.execute_step("battle")
        self.assertFalse(executor.is_executing)

    def test_cancel(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        executor.start_pattern("close_popup")
        self.assertTrue(executor.is_executing)
        executor.cancel()
        self.assertFalse(executor.is_executing)

    def test_success_stats_tracked(self):
        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=self._read_text,
        )
        pattern = self.db.get("close_popup")
        self.assertEqual(pattern.use_count, 0)
        self.assertEqual(pattern.success_count, 0)

        executor.start_pattern("close_popup")
        executor.execute_step("popup_reward")  # step 1
        executor.execute_step("popup_reward")  # step 2 -> completes

        self.assertEqual(pattern.use_count, 1)
        self.assertEqual(pattern.success_count, 1)
        self.assertAlmostEqual(pattern.success_rate, 1.0)

    def test_ocr_text_match(self):
        """PatternExecutor should find target by OCR text when available."""
        def read_text_with_results(path):
            return [
                ("보상 받기", 0.9, 1200, 300),
                ("확인", 0.95, 1400, 540),
            ]

        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=read_text_with_results,
        )
        executor.start_pattern("close_popup")

        # Create a fake screenshot path
        fake_ss = self.tmpdir / "test.png"
        fake_ss.write_bytes(b"\x89PNG" + b"\x00" * 100)

        # Step 1: should match "보상" via OCR at (300, 1200)
        result = executor.execute_step("popup_reward", screenshot_path=fake_ss)
        self.assertIsNotNone(result)
        self.assertIn("ocr:", result)
        self.assertEqual(self.taps[0], (300, 1200))  # OCR position, not fallback

    def test_intent_keyword_match(self):
        """PatternExecutor should find target by intent keywords."""
        # Add a pattern with intent but no target_text
        self.db.add(ActionPattern(
            name="confirm_dialog",
            category="popup",
            trigger_screen="dialog",
            steps=[
                ActionStep(
                    screen_type="dialog",
                    intent="confirm",  # Will search for "확인", "ok", etc.
                    action_type="tap",
                    fallback_x=540, fallback_y=960,
                ),
            ],
        ))

        def read_text_with_results(path):
            return [
                ("취소", 0.9, 800, 300),
                ("확인", 0.95, 800, 700),
            ]

        executor = PatternExecutor(
            pattern_db=self.db,
            tap_fn=self._tap,
            read_text_fn=read_text_with_results,
        )
        executor.start_pattern("confirm_dialog")

        fake_ss = self.tmpdir / "test.png"
        fake_ss.write_bytes(b"\x89PNG" + b"\x00" * 100)

        result = executor.execute_step("dialog", screenshot_path=fake_ss)
        self.assertIsNotNone(result)
        self.assertIn("intent:", result)
        # Should have tapped "확인" position, not "취소"
        self.assertEqual(self.taps[0], (700, 800))


class TestPlayEnginePatternIntegration(unittest.TestCase):
    """Test PatternExecutor integration in PlayEngine."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self.taps = []
        self._ss_count = 0

    def tearDown(self):
        self._tmpdir.cleanup()

    def _screenshot(self, label):
        self._ss_count += 1
        p = self.tmpdir / f"{self._ss_count}.png"
        p.write_bytes(b"\x89PNG" + b"\x00" * 100)
        return p

    def _tap(self, x, y, wait=0):
        self.taps.append((x, y))

    def test_pattern_executes_before_resolver(self):
        """Pattern executor should fire between GOAP and ScreenActionResolver."""
        from virtual_player.play_engine import PlayEngine

        # Create pattern DB with a matching pattern
        db = PatternDB(self.tmpdir / "db.json")
        db.add(ActionPattern(
            name="auto_battle",
            category="quest",
            trigger_screen="battle",
            steps=[
                ActionStep(
                    screen_type="battle",
                    intent="tap_button",
                    target_desc="Auto-battle button",
                    action_type="tap",
                    fallback_x=900, fallback_y=1800,
                    wait_after=0.5,
                ),
            ],
        ))

        executor = PatternExecutor(
            pattern_db=db,
            tap_fn=self._tap,
            read_text_fn=lambda p: [],
        )

        engine = PlayEngine(
            genre="rpg",
            screenshot_fn=self._screenshot,
            tap_fn=self._tap,
            detect_screen_fn=lambda p: "battle",  # Always battle screen
            read_text_fn=lambda p: [],
            play_duration=3,
            screen_width=1080,
            screen_height=1920,
            temp_dir=self.tmpdir,
            pattern_executor=executor,
        )

        result = engine.run()
        # Pattern actions should be in the executed list
        pattern_actions = [a for a in result["actions_executed"]
                          if a.startswith("pattern:")]
        self.assertGreater(len(pattern_actions), 0,
                          "PatternExecutor should have fired at least once")
        # Auto-battle button tap should be in taps
        self.assertIn((900, 1800), self.taps)


if __name__ == "__main__":
    unittest.main()
