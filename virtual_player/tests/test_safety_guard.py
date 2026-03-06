"""Tests for SafetyGuard."""

import unittest

from virtual_player.discovery.safety_guard import SafetyGuard


class TestSafetyGuard(unittest.TestCase):

    def setUp(self):
        self.guard = SafetyGuard()

    def test_safe_no_ocr(self):
        """No OCR text -> always safe."""
        self.assertTrue(self.guard.is_safe_to_tap("lobby", 100, 200))

    def test_safe_normal_text(self):
        """Normal game text -> safe."""
        ocr = [("Start Game", 0.9), ("Settings", 0.8)]
        self.assertTrue(self.guard.is_safe_to_tap("lobby", 100, 200, ocr))

    def test_block_danger_keyword_korean(self):
        """Korean purchase keyword -> blocked."""
        ocr = [("결제 진행", 0.9)]
        self.assertFalse(self.guard.is_safe_to_tap("shop", 300, 400, ocr))
        self.assertEqual(self.guard.blocked_count, 1)

    def test_block_danger_keyword_english(self):
        """English purchase keyword -> blocked."""
        ocr = [("Confirm real money purchase", 0.9)]
        self.assertFalse(self.guard.is_safe_to_tap("shop", 300, 400, ocr))

    def test_block_dollar_sign(self):
        """Dollar sign -> blocked."""
        ocr = ["$4.99"]
        self.assertFalse(self.guard.is_safe_to_tap("shop", 300, 400, ocr))

    def test_block_won_sign(self):
        """Won sign -> blocked."""
        ocr = ["₩5,900"]
        self.assertFalse(self.guard.is_safe_to_tap("shop", 300, 400, ocr))

    def test_caution_keyword_allowed(self):
        """Caution keywords log warning but allow tap."""
        ocr = [("다이아몬드 상점", 0.9)]
        self.assertTrue(self.guard.is_safe_to_tap("shop", 300, 400, ocr))

    def test_resource_limit_first_call(self):
        """First call sets baseline."""
        self.assertTrue(self.guard.check_resource_limit(100000))

    def test_resource_limit_within(self):
        """Spending within limit -> allowed."""
        self.guard.check_resource_limit(100000)
        self.assertTrue(self.guard.check_resource_limit(60000))  # spent 40000

    def test_resource_limit_exceeded(self):
        """Spending beyond limit -> blocked."""
        self.guard.check_resource_limit(100000)
        self.assertFalse(self.guard.check_resource_limit(40000))  # spent 60000

    def test_reset(self):
        """Reset clears resource tracking and blocked count."""
        self.guard.check_resource_limit(100000)
        self.guard.blocked_count = 5
        self.guard.reset()
        self.assertEqual(self.guard.blocked_count, 0)
        # After reset, next call should set new baseline
        self.assertTrue(self.guard.check_resource_limit(50000))

    def test_custom_danger_keywords(self):
        """Custom danger keywords should override defaults."""
        guard = SafetyGuard(danger_keywords=["ABORT", "NUKE"])
        # Default keyword should NOT block
        ocr = ["결제 진행"]
        self.assertTrue(guard.is_safe_to_tap("shop", 100, 200, ocr))
        # Custom keyword should block
        ocr = ["ABORT mission"]
        self.assertFalse(guard.is_safe_to_tap("shop", 100, 200, ocr))

    def test_plain_string_ocr(self):
        """OCR items as plain strings should work."""
        ocr = ["Play", "Settings", "real money purchase"]
        self.assertFalse(self.guard.is_safe_to_tap("shop", 100, 200, ocr))

    def test_mixed_ocr_formats(self):
        """Mix of tuples and strings should work."""
        ocr = [("Play", 0.9), "Settings", ("$5.99", 0.8, 100, 200)]
        self.assertFalse(self.guard.is_safe_to_tap("shop", 100, 200, ocr))


if __name__ == "__main__":
    unittest.main()
