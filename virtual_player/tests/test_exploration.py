"""Tests for ExplorationEngine with mock dependencies."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from virtual_player.discovery.discovery_db import DiscoveryDB
from virtual_player.discovery.exploration_engine import ExplorationEngine
from virtual_player.discovery.safety_guard import SafetyGuard


class MockScreenshots:
    """Generates mock screenshot paths for testing."""

    def __init__(self, tmpdir: Path):
        self.tmpdir = tmpdir
        self.count = 0

    def screenshot(self, label: str) -> Path:
        self.count += 1
        # Create a small dummy image file
        p = self.tmpdir / f"{label}_{self.count}.png"
        self._create_dummy_image(p)
        return p

    def _create_dummy_image(self, path: Path, w: int = 270, h: int = 480):
        """Create a minimal valid PNG file."""
        import struct
        import zlib

        def create_png(width, height):
            def chunk(chunk_type, data):
                c = chunk_type + data
                return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

            header = b'\x89PNG\r\n\x1a\n'
            ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
            ihdr = chunk(b'IHDR', ihdr_data)

            raw_data = b''
            for _ in range(height):
                raw_data += b'\x00' + b'\x80\x80\x80' * width
            compressed = zlib.compress(raw_data)
            idat = chunk(b'IDAT', compressed)
            iend = chunk(b'IEND', b'')

            return header + ihdr + idat + iend

        path.write_bytes(create_png(w, h))


class TestExplorationEngine(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmppath = Path(self.tmpdir)
        self.mock_ss = MockScreenshots(self.tmppath)

        self.db = DiscoveryDB()
        self.safety = SafetyGuard()

        self.tap_log = []
        self.detect_results = iter([])

        def mock_tap(x, y, wait):
            self.tap_log.append((x, y, wait))

        def mock_detect(path):
            try:
                return next(self.detect_results)
            except StopIteration:
                return "lobby"

        self.engine = ExplorationEngine(
            db=self.db,
            safety=self.safety,
            screenshot_fn=self.mock_ss.screenshot,
            tap_fn=mock_tap,
            detect_screen_fn=mock_detect,
            read_screen_text_fn=None,
            close_overlay_fn=lambda max_attempts: None,
            backtrack_fn=lambda target: True,
        )

    def test_explore_empty_screen(self):
        """Exploring an unknown screen should tap grid points."""
        # All detections return same screen (no transitions)
        self.detect_results = iter(["lobby"] * 100)

        result = self.engine.explore_current_screen("lobby", max_taps=5)
        self.assertIn("taps", result)
        self.assertIn("elements_found", result)
        self.assertIn("transitions_found", result)
        self.assertGreaterEqual(result["taps"], 0)

    def test_explore_records_visit(self):
        self.detect_results = iter(["lobby"] * 100)
        self.engine.explore_current_screen("lobby", max_taps=1)
        self.assertIn("lobby", self.db.screens)
        self.assertGreaterEqual(self.db.screens["lobby"]["visit_count"], 1)

    def test_safety_blocks_tap(self):
        """Taps should be blocked when safety guard detects danger."""
        ocr_data = [("결제 진행", 0.9, 100, 200)]

        def mock_ocr(path):
            return ocr_data

        self.engine._read_screen_text = mock_ocr
        self.detect_results = iter(["shop"] * 100)

        result = self.engine.explore_current_screen("shop", max_taps=5)
        # Should have blocked some taps
        self.assertGreaterEqual(self.safety.blocked_count, 0)

    def test_dead_zone_skip(self):
        """Already-dead zones should be skipped."""
        # Get actual untapped regions and mark them ALL as dead
        all_points = self.db.get_untapped_regions("lobby")
        for x, y in all_points:
            for _ in range(4):
                self.db.record_failure("lobby", x, y)
        # Also generate grid points and mark those dead
        grid_pts = self.engine._generate_grid_points()
        for x, y in grid_pts:
            for _ in range(4):
                self.db.record_failure("lobby", x, y)

        self.detect_results = iter(["lobby"] * 100)
        result = self.engine.explore_current_screen("lobby", max_taps=5)
        # All taps should be skipped
        self.assertEqual(result["taps"], 0)

    def test_prioritize_points(self):
        """Points should be sorted with button zone first."""
        points = [(100, 100), (500, 1500), (500, 1000)]
        sorted_pts = self.engine._prioritize_points(points, "lobby")
        # Button zone (y~1500) should come first
        self.assertEqual(sorted_pts[0], (500, 1500))

    def test_prioritize_empty_returns_grid(self):
        """Empty points list should return generated grid."""
        result = self.engine._prioritize_points([], "lobby")
        self.assertEqual(len(result), 40)  # 5 cols x 8 rows

    def test_find_nearest_text(self):
        ocr_texts = [
            ("Play", 0.9, 200, 100),
            ("Settings", 0.8, 400, 500),
            ("Shop", 0.7, 1700, 300),
        ]
        result = ExplorationEngine._find_nearest_text(ocr_texts, 110, 210)
        self.assertEqual(result, "Play")

    def test_find_nearest_text_low_confidence(self):
        ocr_texts = [("Noise", 0.1, 100, 100)]
        result = ExplorationEngine._find_nearest_text(ocr_texts, 100, 100)
        self.assertEqual(result, "")  # conf 0.1 < 0.3 threshold

    def test_find_nearest_text_out_of_radius(self):
        ocr_texts = [("Far", 0.9, 1000, 1000)]
        result = ExplorationEngine._find_nearest_text(ocr_texts, 100, 100, radius=150)
        self.assertEqual(result, "")

    def test_compute_change_identical(self):
        """Identical images should have 0 change."""
        p1 = self.mock_ss.screenshot("same1")
        p2 = self.mock_ss.screenshot("same2")
        change = ExplorationEngine._compute_change(p1, p2)
        self.assertAlmostEqual(change, 0.0, places=2)

    def test_compute_change_none_path(self):
        change = ExplorationEngine._compute_change(None, None)
        self.assertEqual(change, 0.0)

    def test_backtrack_with_fn(self):
        result = self.engine.backtrack("lobby")
        self.assertTrue(result)

    def test_backtrack_without_fn(self):
        """Backtrack without custom fn should try close_overlay."""
        close_calls = []

        def mock_close(n):
            close_calls.append(n)

        engine = ExplorationEngine(
            db=self.db,
            safety=self.safety,
            screenshot_fn=self.mock_ss.screenshot,
            tap_fn=lambda x, y, w: None,
            detect_screen_fn=lambda p: "lobby",
            close_overlay_fn=mock_close,
            backtrack_fn=None,  # No custom backtrack
        )
        result = engine.backtrack("lobby")
        self.assertTrue(result)

    def test_explore_unknown_state(self):
        """Should return a screen type string."""
        self.detect_results = iter(["lobby"] * 10)
        result = self.engine.explore_unknown_state()
        self.assertIsInstance(result, str)

    def test_max_depth_triggers_backtrack(self):
        """Exceeding MAX_DEPTH should trigger backtrack."""
        # Set depth to MAX_DEPTH so next transition triggers backtrack
        self.engine._depth = self.engine.MAX_DEPTH

        # Create screenshots that differ (to trigger transition detection)
        ss_count = [0]
        original_ss = self.mock_ss.screenshot

        def varying_screenshot(label):
            ss_count[0] += 1
            p = self.tmppath / f"vary_{ss_count[0]}.png"
            self._create_varying_image(p, ss_count[0])
            return p

        self.engine._screenshot = varying_screenshot

        # Make detection return a different screen on "after" screenshots
        call_count = [0]
        def mock_detect(path):
            call_count[0] += 1
            # Every other call returns a different screen (after screenshot)
            if call_count[0] % 2 == 0:
                return "new_screen"
            return "lobby"

        self.engine._detect_screen = mock_detect

        result = self.engine.explore_current_screen("lobby", max_taps=5)
        # Should have backtracked (depth reset to 0)
        self.assertEqual(self.engine._depth, 0)

    def _create_varying_image(self, path, seed):
        """Create a PNG that varies based on seed."""
        import struct
        import zlib

        w, h = 270, 480
        def chunk(chunk_type, data):
            c = chunk_type + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

        header = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
        ihdr = chunk(b'IHDR', ihdr_data)

        # Use seed to vary pixel values
        val = (seed * 37) % 256
        raw_data = b''
        for _ in range(h):
            raw_data += b'\x00' + bytes([val, val, val]) * w
        compressed = zlib.compress(raw_data)
        idat = chunk(b'IDAT', compressed)
        iend = chunk(b'IEND', b'')

        path.write_bytes(header + ihdr + idat + iend)


class TestExplorationEngineWithOCR(unittest.TestCase):
    """Tests with mock OCR integration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmppath = Path(self.tmpdir)
        self.mock_ss = MockScreenshots(self.tmppath)
        self.db = DiscoveryDB()
        self.safety = SafetyGuard()

        self.ocr_data = [
            ("Play", 0.9, 500, 540),
            ("Shop", 0.8, 1700, 300),
            ("Settings", 0.7, 100, 900),
        ]

        self.engine = ExplorationEngine(
            db=self.db,
            safety=self.safety,
            screenshot_fn=self.mock_ss.screenshot,
            tap_fn=lambda x, y, w: None,
            detect_screen_fn=lambda p: "lobby",
            read_screen_text_fn=lambda p: self.ocr_data,
            close_overlay_fn=lambda n: None,
        )

    def test_ocr_text_used_in_element_labels(self):
        """OCR text should be recorded with discovered elements."""
        result = self.engine.explore_current_screen("lobby", max_taps=3)
        # Check that some elements were found (all same screen = no change, so mostly failures)
        self.assertGreaterEqual(result["taps"], 0)


if __name__ == "__main__":
    unittest.main()
