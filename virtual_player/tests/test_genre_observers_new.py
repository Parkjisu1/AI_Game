"""Tests for new genre observers (idle, merge, slg)."""

import tempfile
import unittest
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock


class TestIdleObservers(unittest.TestCase):
    """Test idle genre observers."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self.observations: Dict[str, List] = {}
        self._count = 0

    def tearDown(self):
        self._tmpdir.cleanup()

    def _capture(self, label="") -> Optional[Path]:
        self._count += 1
        p = self.tmpdir / f"{self._count}.png"
        p.write_bytes(b"\x89PNG" + b"\x00" * 100)
        return p

    def _ocr_with_offline(self, path):
        return [
            ("Offline Reward", 0.9, 300, 200),
            ("1.2K/s", 0.8, 400, 100),
        ]

    def _ocr_with_upgrade(self, path):
        return [
            ("Upgrade Lv.15", 0.9, 300, 200),
            ("Cost: 500K", 0.8, 400, 200),
        ]

    def _ocr_with_auto(self, path):
        return [
            ("Auto x2", 0.9, 100, 100),
            ("Idle 8h", 0.8, 200, 100),
        ]

    def test_idle_progress_observer(self):
        """IdleProgressObserver should detect offline rewards."""
        from virtual_player.observers.idle_observers import IdleProgressObserver
        obs = IdleProgressObserver(self._capture, self.observations, ocr_fn=self._ocr_with_offline)
        obs.run()
        # Should have recorded observations
        self.assertGreater(len(self.observations), 0)

    def test_idle_upgrade_observer(self):
        """IdleUpgradeObserver should detect upgrade info."""
        from virtual_player.observers.idle_observers import IdleUpgradeObserver
        obs = IdleUpgradeObserver(self._capture, self.observations, ocr_fn=self._ocr_with_upgrade)
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_idle_automation_observer(self):
        """IdleAutomationObserver should detect auto mode."""
        from virtual_player.observers.idle_observers import IdleAutomationObserver
        obs = IdleAutomationObserver(self._capture, self.observations, ocr_fn=self._ocr_with_auto)
        obs.run()
        self.assertGreater(len(self.observations), 0)


class TestMergeObservers(unittest.TestCase):
    """Test merge genre observers."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self.observations: Dict[str, List] = {}
        self._count = 0

    def tearDown(self):
        self._tmpdir.cleanup()

    def _capture(self, label="") -> Optional[Path]:
        self._count += 1
        p = self.tmpdir / f"{self._count}.png"
        p.write_bytes(b"\x89PNG" + b"\x00" * 100)
        return p

    def _ocr_with_orders(self, path):
        return [
            ("Order 1/3", 0.9, 200, 300),
            ("Deliver", 0.8, 400, 300),
        ]

    def _ocr_with_energy(self, path):
        return [
            ("Energy 50/100", 0.9, 50, 500),
        ]

    def test_merge_board_observer_with_snapshots(self):
        """MergeBoardObserver should analyze recorded board snapshots."""
        from virtual_player.observers.merge_observers import MergeBoardObserver
        obs = MergeBoardObserver(self._capture, self.observations)
        obs.record_board_snapshot({"board_size": 25, "item_count": 18, "tiers": [1, 2, 3], "empty_cells": 7})
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_merge_order_observer(self):
        """MergeOrderObserver should detect order keywords."""
        from virtual_player.observers.merge_observers import MergeOrderObserver
        obs = MergeOrderObserver(self._capture, self.observations, ocr_fn=self._ocr_with_orders)
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_merge_energy_observer(self):
        """MergeEnergyObserver should extract energy values."""
        from virtual_player.observers.merge_observers import MergeEnergyObserver
        obs = MergeEnergyObserver(self._capture, self.observations, ocr_fn=self._ocr_with_energy)
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_merge_order_completion_rate(self):
        """MergeOrderObserver should track completion rate."""
        from virtual_player.observers.merge_observers import MergeOrderObserver
        obs = MergeOrderObserver(self._capture, self.observations, ocr_fn=self._ocr_with_orders)
        obs.record_order_result(True)
        obs.record_order_result(True)
        obs.record_order_result(False)
        obs.run()
        # Should have recorded order_completion_rate
        self.assertIn("order_completion_rate", self.observations)


class TestSLGObservers(unittest.TestCase):
    """Test SLG genre observers."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmpdir.name)
        self.observations: Dict[str, List] = {}
        self._count = 0

    def tearDown(self):
        self._tmpdir.cleanup()

    def _capture(self, label="") -> Optional[Path]:
        self._count += 1
        p = self.tmpdir / f"{self._count}.png"
        p.write_bytes(b"\x89PNG" + b"\x00" * 100)
        return p

    def _ocr_with_resources(self, path):
        return [
            ("Food: 15.2K", 0.9, 30, 100),
            ("Wood: 8.5K", 0.9, 30, 300),
            ("Gold: 2.3M", 0.9, 30, 500),
        ]

    def _ocr_with_military(self, path):
        return [
            ("Troops: 5000", 0.9, 200, 300),
            ("Power: 125K", 0.8, 200, 500),
            ("March 2/3", 0.7, 300, 300),
        ]

    def _ocr_with_territory(self, path):
        return [
            ("Castle Lv.10", 0.9, 100, 200),
            ("Alliance Members: 45", 0.8, 200, 200),
            ("Territory: 12", 0.7, 300, 200),
        ]

    def test_slg_resource_observer(self):
        """SLGResourceObserver should extract resource values."""
        from virtual_player.observers.slg_observers import SLGResourceObserver
        obs = SLGResourceObserver(self._capture, self.observations, ocr_fn=self._ocr_with_resources)
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_slg_military_observer(self):
        """SLGMilitaryObserver should detect military keywords."""
        from virtual_player.observers.slg_observers import SLGMilitaryObserver
        obs = SLGMilitaryObserver(self._capture, self.observations, ocr_fn=self._ocr_with_military)
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_slg_territory_observer(self):
        """SLGTerritoryObserver should detect territory/castle info."""
        from virtual_player.observers.slg_observers import SLGTerritoryObserver
        obs = SLGTerritoryObserver(self._capture, self.observations, ocr_fn=self._ocr_with_territory)
        obs.run()
        self.assertGreater(len(self.observations), 0)

    def test_slg_resource_snapshots(self):
        """SLGResourceObserver should analyze recorded snapshots."""
        from virtual_player.observers.slg_observers import SLGResourceObserver
        obs = SLGResourceObserver(self._capture, self.observations, ocr_fn=self._ocr_with_resources)
        obs.record_resource_snapshot({"food": 15000, "wood": 8500, "gold": 2300000})
        obs.record_resource_snapshot({"food": 16000, "wood": 9000, "gold": 2400000})
        obs.run()
        self.assertGreater(len(self.observations), 0)


if __name__ == "__main__":
    unittest.main()
