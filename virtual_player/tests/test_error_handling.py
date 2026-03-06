"""Tests for WS5 -- Error handling and robustness."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from virtual_player.test_orchestrator import TestOrchestrator


class MockErrorOrchestrator(TestOrchestrator):
    """Orchestrator for testing error handling paths."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _screenshot(self, label=""):
        self._screenshot_count += 1
        path = self._temp_dir / f"{self._screenshot_count:04d}_{label}.png"
        path.write_bytes(b"\x89PNG" + b"\x00" * 100)
        return path

    def _tap(self, x, y, wait=0.0):
        pass


class TestADBRetry(unittest.TestCase):
    """Test ADB retry logic."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_orch(self):
        orch = MockErrorOrchestrator(
            package_name="com.test.retry",
            adb_path="echo",  # dummy
            dry_run=True,
        )
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)
        return orch

    def test_adb_returns_none_on_all_timeouts(self):
        """ADB should return None after all retries timeout."""
        import subprocess
        orch = self._make_orch()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 10)):
            result = orch._adb(["shell", "test"], retries=1)
        self.assertIsNone(result)

    def test_adb_succeeds_on_retry(self):
        """ADB should succeed if retry works."""
        import subprocess
        mock_success = MagicMock()
        mock_success.returncode = 0
        mock_success.stdout = "ok"

        orch = self._make_orch()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise subprocess.TimeoutExpired("adb", 10)
            return mock_success

        with patch("subprocess.run", side_effect=side_effect):
            result = orch._adb(["shell", "test"], retries=2)

        self.assertIsNotNone(result)
        self.assertEqual(result.returncode, 0)

    def test_adb_reconnect_called_on_failure(self):
        """_adb_reconnect should be called on non-zero return."""
        orch = self._make_orch()
        mock_fail = MagicMock()
        mock_fail.returncode = 1

        mock_success = MagicMock()
        mock_success.returncode = 0

        calls = []

        def run_side_effect(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args", []))
            if len(calls) <= 2:  # First call + reconnect
                return mock_fail
            return mock_success

        with patch("subprocess.run", side_effect=run_side_effect):
            orch._adb(["shell", "test"], retries=2)

        # Should have called reconnect at some point
        reconnect_calls = [c for c in calls if "reconnect" in str(c)]
        self.assertGreater(len(reconnect_calls), 0)


class TestScreenshotCleanup(unittest.TestCase):
    """Test screenshot disk cleanup."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_play_engine_cleanup(self):
        """PlayEngine should clean up old screenshots."""
        from virtual_player.play_engine import PlayEngine

        engine = PlayEngine(
            genre="rpg",
            screenshot_fn=lambda l: None,
            tap_fn=lambda x, y, w=0: None,
            detect_screen_fn=lambda p: "unknown",
            read_text_fn=lambda p: [],
            play_duration=1,
            screen_width=1080,
            screen_height=1920,
            temp_dir=self.tmpdir,
        )
        engine.MAX_SCREENSHOTS = 5

        # Create 20 fake screenshots
        for i in range(20):
            (self.tmpdir / f"play_{i:04d}.png").write_bytes(b"fake")

        engine._cleanup_old_screenshots()
        remaining = list(self.tmpdir.glob("*.png"))
        self.assertLessEqual(len(remaining), 10)


class TestStuckDetection(unittest.TestCase):
    """Test stuck detection in PlayEngine."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self._count = 0

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_stuck_triggers_escape(self):
        """Stuck detection should trigger escape sequence after threshold."""
        from virtual_player.play_engine import PlayEngine

        taps = []

        def screenshot(label):
            self._count += 1
            p = self.tmpdir / f"{self._count}.png"
            p.write_bytes(b"\x89PNG" + b"\x00" * 100)
            return p

        engine = PlayEngine(
            genre="rpg",
            screenshot_fn=screenshot,
            tap_fn=lambda x, y, w=0: taps.append((x, y)),
            detect_screen_fn=lambda p: "stuck_screen",  # Always same screen
            read_text_fn=lambda p: [],
            play_duration=3,
            screen_width=1080,
            screen_height=1920,
            temp_dir=self.tmpdir,
        )
        engine.STUCK_THRESHOLD = 3

        result = engine.run()
        # Should have completed (not hung)
        self.assertGreater(result["tick_count"], 0)
        # Should have tapped in escape sequence (fallback positions include 540,1870 / 1020,80 / 60,80)
        escape_taps = [(540, 1870), (1020, 80), (60, 80)]
        self.assertTrue(any(
            (t[0], t[1]) in escape_taps for t in taps
        ), f"Expected one of {escape_taps} in taps, got {taps[:10]}")


class TestOCRFallback(unittest.TestCase):
    """Test OCR graceful fallback."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_read_text_without_init(self):
        """_read_screen_text should return [] without perception init."""
        orch = MockErrorOrchestrator(
            package_name="com.test.ocr",
            dry_run=True,
        )
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)

        path = orch._temp_dir / "test.png"
        path.write_bytes(b"\x89PNG" + b"\x00" * 100)
        result = orch._read_screen_text(path)
        self.assertEqual(result, [])

    def test_detect_screen_without_init(self):
        """_detect_screen should return 'unknown' without perception init."""
        orch = MockErrorOrchestrator(
            package_name="com.test.detect",
            dry_run=True,
        )
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)

        path = orch._temp_dir / "test.png"
        path.write_bytes(b"\x89PNG" + b"\x00" * 100)
        result = orch._detect_screen(path)
        self.assertEqual(result, "unknown")


if __name__ == "__main__":
    unittest.main()
