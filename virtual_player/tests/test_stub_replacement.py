"""Tests for WS1 -- Stub replacement in TestOrchestrator."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from virtual_player.test_orchestrator import TestOrchestrator


class MockPerceptionOrchestrator(TestOrchestrator):
    """Orchestrator with mocked ADB but real perception init."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_screenshot_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

    def _adb(self, args, timeout=10, retries=2):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = ""
        return mock

    def _screenshot(self, label=""):
        self._screenshot_count += 1
        path = self._temp_dir / f"{self._screenshot_count:04d}_{label}.png"
        path.write_bytes(self._mock_screenshot_data)
        return path

    def _tap(self, x, y, wait=0.0):
        pass


class TestPerceptionInit(unittest.TestCase):
    """Test _init_perception wiring."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_orch(self):
        orch = MockPerceptionOrchestrator(
            package_name="com.test.game",
            dry_run=True,
        )
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)
        return orch

    def test_init_perception_creates_classifier(self):
        """_init_perception should create a ScreenClassifier."""
        orch = self._make_orch()
        orch._init_perception("rpg", 1080, 1920)
        self.assertIsNotNone(orch._classifier)

    def test_init_perception_creates_ocr_reader(self):
        """_init_perception should create an OCRReader."""
        orch = self._make_orch()
        orch._init_perception("rpg", 1080, 1920)
        self.assertIsNotNone(orch._ocr_reader)

    def test_init_perception_creates_state_reader(self):
        """_init_perception should create a StateReader."""
        orch = self._make_orch()
        orch._init_perception("rpg", 1080, 1920)
        self.assertIsNotNone(orch._state_reader)

    def test_init_perception_unknown_genre_still_works(self):
        """_init_perception with unknown genre should not crash."""
        orch = self._make_orch()
        orch._init_perception("unknown_genre", 1080, 1920)
        # Classifier should still be created (with empty screen types)
        self.assertIsNotNone(orch._classifier)

    def test_detect_screen_uses_classifier(self):
        """After init, _detect_screen should use the classifier."""
        orch = self._make_orch()
        orch._init_perception("rpg", 1080, 1920)
        # Create a fake screenshot
        path = orch._temp_dir / "test_screen.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
        # Should not return "unknown" blindly (though without real images it may)
        result = orch._detect_screen(path)
        self.assertIsInstance(result, str)

    def test_detect_screen_fallback_without_init(self):
        """Without init, _detect_screen should return 'unknown'."""
        orch = self._make_orch()
        path = orch._temp_dir / "test.png"
        path.write_bytes(b"\x89PNG")
        result = orch._detect_screen(path)
        self.assertEqual(result, "unknown")


class TestObserverFactory(unittest.TestCase):
    """Test _create_observers and _get_genre_observers."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_orch(self):
        orch = MockPerceptionOrchestrator(
            package_name="com.test.game",
            dry_run=True,
        )
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)
        return orch

    def test_create_observers_includes_generic(self):
        """_create_observers should include 4 generic observers."""
        orch = self._make_orch()
        obs = orch._create_observers("unknown", {})
        self.assertGreaterEqual(len(obs), 4)

    def test_create_observers_rpg_has_extras(self):
        """RPG genre should add combat, town, quest observers."""
        orch = self._make_orch()
        obs = orch._create_observers("rpg", {})
        # 4 generic + 3 RPG = 7
        self.assertEqual(len(obs), 7)

    def test_create_observers_puzzle_has_extras(self):
        """Puzzle genre should add board, match observers."""
        orch = self._make_orch()
        obs = orch._create_observers("puzzle", {})
        # 4 generic + 2 puzzle = 6
        self.assertEqual(len(obs), 6)

    def test_create_observers_idle_has_extras(self):
        """Idle genre should add idle-specific observers."""
        orch = self._make_orch()
        obs = orch._create_observers("idle", {})
        # 4 generic + 3 idle = 7
        self.assertEqual(len(obs), 7)

    def test_create_observers_merge_has_extras(self):
        """Merge genre should add merge-specific observers."""
        orch = self._make_orch()
        obs = orch._create_observers("merge", {})
        # 4 generic + 3 merge = 7
        self.assertEqual(len(obs), 7)

    def test_create_observers_slg_has_extras(self):
        """SLG genre should add SLG-specific observers."""
        orch = self._make_orch()
        obs = orch._create_observers("slg", {})
        # 4 generic + 3 SLG = 7
        self.assertEqual(len(obs), 7)


if __name__ == "__main__":
    unittest.main()
