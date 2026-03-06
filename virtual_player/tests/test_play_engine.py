"""Tests for PlayEngine -- Active game play loop."""

import tempfile
import time
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch


class TestPlayEngine(unittest.TestCase):
    """Test the PlayEngine play loop."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self._screenshot_count = 0
        self._tap_log: List[Tuple[int, int]] = []

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_screenshot(self, label: str = "") -> Optional[Path]:
        self._screenshot_count += 1
        path = self.tmpdir / f"{self._screenshot_count:04d}_{label}.png"
        # Minimal PNG bytes
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return path

    def _tap(self, x: int, y: int, wait: float = 0.0):
        self._tap_log.append((x, y))

    def _detect_screen(self, path: Path) -> str:
        return "lobby"

    def _read_text(self, path: Path) -> list:
        return [("Play", 0.9, 960, 540)]

    def _make_engine(self, duration: int = 2, **kwargs):
        from virtual_player.play_engine import PlayEngine
        return PlayEngine(
            genre="rpg",
            screenshot_fn=self._make_screenshot,
            tap_fn=self._tap,
            detect_screen_fn=kwargs.get("detect_fn", self._detect_screen),
            read_text_fn=kwargs.get("read_fn", self._read_text),
            play_duration=duration,
            screen_width=1080,
            screen_height=1920,
            temp_dir=self.tmpdir,
            **{k: v for k, v in kwargs.items() if k not in ("detect_fn", "read_fn")},
        )

    def test_run_returns_expected_keys(self):
        """run() should return a dict with standard keys."""
        engine = self._make_engine(duration=1)
        result = engine.run()
        self.assertIn("tick_count", result)
        self.assertIn("screens_visited", result)
        self.assertIn("actions_executed", result)
        self.assertIn("duration", result)
        self.assertGreater(result["tick_count"], 0)

    def test_duration_respected(self):
        """Engine should stop after play_duration seconds."""
        engine = self._make_engine(duration=2)
        start = time.time()
        result = engine.run()
        elapsed = time.time() - start
        self.assertGreaterEqual(elapsed, 1.5)
        self.assertLessEqual(elapsed, 10.0)  # generous upper bound

    def test_screenshots_taken(self):
        """Engine should take screenshots during play."""
        engine = self._make_engine(duration=1)
        engine.run()
        self.assertGreater(self._screenshot_count, 0)

    def test_screens_visited_tracked(self):
        """Engine should track which screens were visited."""
        engine = self._make_engine(duration=1)
        result = engine.run()
        self.assertIn("lobby", result["screens_visited"])

    def test_explore_fallback_used(self):
        """Without a reasoner, engine should use explore_fallback."""
        engine = self._make_engine(duration=1)
        result = engine.run()
        explore_actions = [a for a in result["actions_executed"] if a.startswith("explore_")]
        self.assertGreater(len(explore_actions), 0)

    def test_stuck_detection(self):
        """Engine should detect stuck state after STUCK_THRESHOLD same screens."""
        engine = self._make_engine(duration=3)
        engine.STUCK_THRESHOLD = 3
        result = engine.run()
        # Should still complete without hanging
        self.assertIn("tick_count", result)

    def test_observers_called(self):
        """Observers should be called during play."""
        mock_observer = MagicMock()
        mock_observer.name = "MockObs"
        engine = self._make_engine(duration=2, observers=[mock_observer])
        engine._observer_interval = 1  # Every tick
        engine.run()
        self.assertTrue(mock_observer.run.called)

    def test_cleanup_screenshots(self):
        """Old screenshots should be cleaned up."""
        engine = self._make_engine(duration=1)
        engine.MAX_SCREENSHOTS = 5
        # Create many screenshot files
        for i in range(20):
            (self.tmpdir / f"play_{i:04d}.png").write_bytes(b"fake")
        engine._cleanup_old_screenshots()
        remaining = list(self.tmpdir.glob("*.png"))
        self.assertLessEqual(len(remaining), 10)  # Some removed


class TestPlayEngineWithReasoner(unittest.TestCase):
    """Test PlayEngine with a mock GOAP reasoner."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_reasoner_actions_executed(self):
        """When reasoner returns actions, they should be executed."""
        from virtual_player.play_engine import PlayEngine

        mock_action = MagicMock()
        mock_action.name = "test_action"
        mock_action.required_screen = None
        mock_action.metadata = {}

        mock_reasoner = MagicMock()
        mock_reasoner.decide.return_value = mock_action

        count = 0

        def screenshot(label):
            nonlocal count
            count += 1
            p = self.tmpdir / f"{count}.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            return p

        engine = PlayEngine(
            genre="rpg",
            screenshot_fn=screenshot,
            tap_fn=lambda x, y, w=0: None,
            detect_screen_fn=lambda p: "lobby",
            read_text_fn=lambda p: [],
            reasoner=mock_reasoner,
            play_duration=1,
            screen_width=1080,
            screen_height=1920,
            temp_dir=self.tmpdir,
        )

        result = engine.run()
        self.assertIn("test_action", result["actions_executed"])
        self.assertTrue(mock_reasoner.decide.called)


if __name__ == "__main__":
    unittest.main()
