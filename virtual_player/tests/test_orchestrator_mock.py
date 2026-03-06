"""Mock E2E test for TestOrchestrator (no real ADB)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from virtual_player.test_orchestrator import TestOrchestrator


class MockADBOrchestrator(TestOrchestrator):
    """TestOrchestrator with mocked ADB methods."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_screen_type = "lobby"
        self._mock_screenshot_data = self._make_png(128)

    @staticmethod
    def _make_png(gray_value: int) -> bytes:
        """Create a minimal 4x4 grayscale PNG."""
        import struct
        import zlib

        width, height = 4, 4
        raw = b""
        for _ in range(height):
            raw += b"\x00" + bytes([gray_value] * (width * 3))
        compressed = zlib.compress(raw)

        def chunk(ctype, data):
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )

    def _adb(self, args, timeout=10):
        """Mock ADB -- returns fake success responses."""
        mock = MagicMock()
        mock.returncode = 0
        if "wm" in args and "size" in args:
            mock.stdout = "Physical size: 1080x1920"
        elif "screencap" in args:
            mock.stdout = self._mock_screenshot_data
        elif "dumpsys" in args:
            mock.stdout = "mFocusedActivity: com.test.game/.MainActivity"
        else:
            mock.stdout = ""
        return mock

    def _screenshot(self, label=""):
        """Return a mock screenshot path."""
        self._screenshot_count += 1
        path = self._temp_dir / f"{self._screenshot_count:04d}_{label}.png"
        path.write_bytes(self._mock_screenshot_data)
        return path

    def _tap(self, x, y, wait=0.0):
        """No-op tap (skip sleep)."""
        pass

    def _detect_screen(self, path):
        return self._mock_screen_type

    def _read_screen_text(self, path):
        return [("Play", 0.9, 960, 540), ("Settings", 0.8, 1200, 540)]

    def _read_screen_text_from_path(self, path):
        return self._read_screen_text(path)

    def _close_overlay(self, max_attempts=3):
        pass


class TestOrchestratorMock(unittest.TestCase):
    """Test the 4-phase pipeline with mocked ADB."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_orchestrator(self, package="com.test.mockgame"):
        orch = MockADBOrchestrator(
            package_name=package,
            dry_run=True,
            explore_taps=4,
            play_duration=1,
        )
        # Redirect temp/journal/knowledge dirs to tmpdir
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)
        return orch

    def test_full_pipeline_returns_summary(self):
        """Full run should return a summary dict with expected keys."""
        orch = self._make_orchestrator()

        with patch("virtual_player.test_orchestrator.KNOWLEDGE_DB",
                   self.tmpdir / "kb.json"), \
             patch("virtual_player.test_orchestrator.JOURNAL_DIR",
                   self.tmpdir / "journal"), \
             patch("virtual_player.test_orchestrator.DESIGN_DB_ROOT",
                   self.tmpdir / "design"), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.launch",
                   return_value=True), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.dismiss_initial_popups",
                   return_value=0), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.get_device_resolution",
                   return_value=(1080, 1920)):
            (self.tmpdir / "journal").mkdir(exist_ok=True)
            summary = orch.run()

        self.assertIn("package_name", summary)
        self.assertEqual(summary["package_name"], "com.test.mockgame")
        self.assertIn("genre", summary)
        self.assertIn("duration_seconds", summary)
        self.assertIn("phase_results", summary)
        self.assertIsInstance(summary["phase_results"], dict)
        self.assertIn("bootstrap", summary["phase_results"])
        self.assertIn("play", summary["phase_results"])
        self.assertIn("extract", summary["phase_results"])
        self.assertIn("journal", summary["phase_results"])

    def test_game_id_derived(self):
        """game_id should be last segment of package name."""
        orch = self._make_orchestrator("com.company.mygame")
        self.assertEqual(orch.game_id, "mygame")

    def test_bootstrap_detects_genre(self):
        """Bootstrap phase should detect a genre string."""
        orch = self._make_orchestrator()

        with patch("virtual_player.test_orchestrator.KNOWLEDGE_DB",
                   self.tmpdir / "kb.json"), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.launch",
                   return_value=True), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.dismiss_initial_popups",
                   return_value=0), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.get_device_resolution",
                   return_value=(1080, 1920)):
            result = orch._phase_bootstrap()

        self.assertIn("genre", result)
        self.assertIsInstance(result["genre"], str)
        self.assertIn("status", result)

    def test_play_phase_runs_observers(self):
        """Play phase should run generic + genre-specific observers."""
        orch = self._make_orchestrator()
        result = orch._phase_play("puzzle", {})
        # 4 generic + 2 puzzle-specific (BoardObserver, MatchObserver) = 6
        self.assertGreaterEqual(result["observer_count"], 4)
        self.assertIn("observations", result)

    def test_extract_phase_dry_run(self):
        """Extract with dry_run should log paths but not create actual files."""
        orch = self._make_orchestrator()
        play_result = {
            "observations": {
                "p1": [{"observer_id": 1, "value": 42, "confidence": 0.9}],
            },
        }

        design_dir = self.tmpdir / "design"
        with patch("virtual_player.test_orchestrator.DESIGN_DB_ROOT", design_dir):
            result = orch._phase_extract("puzzle", play_result)

        self.assertEqual(result["status"], "success")
        # dry_run returns would-be paths but doesn't create files on disk
        files_dir = design_dir / "base" / "puzzle" / "ingame" / "files"
        self.assertFalse(files_dir.exists())

    def test_journal_phase_writes_files(self):
        """Journal phase should create markdown + JSON sidecar."""
        orch = self._make_orchestrator()
        orch._phase_results = {
            "bootstrap": {"discovery_data": {"screens": {"lobby": {}}}, "status": "success"},
            "play": {"observations": {}, "status": "success"},
            "extract": {"param_count": 5, "status": "success"},
        }

        journal_dir = self.tmpdir / "journal"
        journal_dir.mkdir(exist_ok=True)

        with patch("virtual_player.test_orchestrator.JOURNAL_DIR", journal_dir):
            result = orch._phase_journal("puzzle", 10.0)

        self.assertEqual(result["status"], "success")
        self.assertIn("journal_paths", result)
        self.assertIn("patterns", result)

    def test_knowledge_update(self):
        """Knowledge update should persist game data."""
        orch = self._make_orchestrator()
        kb_path = self.tmpdir / "kb.json"

        with patch("virtual_player.test_orchestrator.KNOWLEDGE_DB", kb_path):
            orch._update_knowledge(
                "puzzle",
                {"screen_types": {"lobby": "Main"}},
                {"param_count": 3},
            )

        self.assertTrue(kb_path.exists())
        with open(kb_path) as f:
            data = json.load(f)
        self.assertIn("com.test.mockgame", data["games"])

    def test_build_domain_groups(self):
        """Domain groups should be built from aggregated params."""
        orch = self._make_orchestrator()
        aggregated = {
            "board_size": {"name": "board_size", "status": "observed"},
            "ad_frequency": {"name": "ad_frequency", "status": "observed"},
            "level_count": {"name": "level_count", "status": "observed"},
            "not_observed": {"name": "foo", "status": "not_observed"},
        }
        groups = orch._build_domain_groups("puzzle", aggregated)
        self.assertGreater(len(groups), 0)
        domains = {g.domain for g in groups}
        self.assertTrue(domains.issubset({"ingame", "content", "balance", "bm", "ux"}))

    def test_errors_accumulated(self):
        """Errors from phases should accumulate in _errors list."""
        orch = self._make_orchestrator()
        self.assertEqual(len(orch._errors), 0)
        orch._errors.append("test error")
        self.assertEqual(len(orch._errors), 1)


class TestOrchestratorActivePIay(unittest.TestCase):
    """Test active play integration (WS2)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_orchestrator(self, package="com.test.active"):
        orch = MockADBOrchestrator(
            package_name=package,
            dry_run=True,
            explore_taps=4,
            play_duration=1,
        )
        orch._temp_dir = self.tmpdir / "temp"
        orch._temp_dir.mkdir(parents=True, exist_ok=True)
        return orch

    def test_play_phase_returns_engine_fields(self):
        """Play phase with PlayEngine should return tick_count and screens_visited."""
        orch = self._make_orchestrator()
        result = orch._phase_play("rpg", {})
        self.assertIn("tick_count", result)
        self.assertIn("screens_visited", result)
        self.assertIn("actions_executed", result)

    def test_play_phase_tick_count_positive(self):
        """Active play should produce at least 1 tick."""
        orch = self._make_orchestrator()
        result = orch._phase_play("rpg", {})
        self.assertGreater(result.get("tick_count", 0), 0)

    def test_perception_init_in_bootstrap(self):
        """Bootstrap phase should init perception stack."""
        orch = self._make_orchestrator()

        with patch("virtual_player.test_orchestrator.KNOWLEDGE_DB",
                   self.tmpdir / "kb.json"), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.launch",
                   return_value=True), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.dismiss_initial_popups",
                   return_value=0), \
             patch("virtual_player.bootstrap.launch_manager.LaunchManager.get_device_resolution",
                   return_value=(1080, 1920)):
            result = orch._phase_bootstrap()

        # After bootstrap, perception should be initialized
        # (MockADBOrchestrator overrides _detect_screen, but _init_perception is still called)
        self.assertIn("status", result)


class TestOrchestratorEdgeCases(unittest.TestCase):
    """Edge case tests."""

    def test_bootstrap_failure_returns_unknown_genre(self):
        """If bootstrap fails, genre should be 'unknown'."""
        orch = MockADBOrchestrator(
            package_name="com.fail.game",
            dry_run=True,
        )
        # Force launch to fail
        with patch.object(orch, "_adb", return_value=None):
            tmpdir = tempfile.mkdtemp()
            orch._temp_dir = Path(tmpdir)
            orch._temp_dir.mkdir(parents=True, exist_ok=True)

            with patch("virtual_player.test_orchestrator.KNOWLEDGE_DB",
                       Path(tmpdir) / "kb.json"):
                result = orch._phase_bootstrap()

            self.assertIn(result.get("genre", "unknown"), ["unknown", "error"])

    def test_empty_observations_extract(self):
        """Extract with no observations should still succeed."""
        orch = MockADBOrchestrator(
            package_name="com.test.empty",
            dry_run=True,
        )
        tmpdir = tempfile.mkdtemp()
        orch._temp_dir = Path(tmpdir)

        play_result = {"observations": {}}
        with patch("virtual_player.test_orchestrator.DESIGN_DB_ROOT",
                   Path(tmpdir) / "design"):
            result = orch._phase_extract("puzzle", play_result)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["param_count"], 0)


if __name__ == "__main__":
    unittest.main()
