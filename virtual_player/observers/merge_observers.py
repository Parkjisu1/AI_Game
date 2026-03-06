"""
Merge Observers -- Merge Genre-Specific Parameter Observers
============================================================
Board state, order tracking, energy management for Merge games.
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import ObserverBase, ScreenCaptureFn

logger = logging.getLogger(__name__)


class MergeBoardObserver(ObserverBase):
    """Observes merge board: grid size, item count, tier distribution, empty cells."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(5, "MergeBoard", "ingame", capture_fn, observations)
        self._ocr = ocr_fn
        self._board_snapshots: List[Dict] = []

    def record_board_snapshot(self, snapshot: Dict) -> None:
        """Record a board snapshot dict with keys: board_size, items, tiers, empty_cells."""
        self._board_snapshots.append(snapshot)

    def run(self) -> None:
        p = self.screenshot("merge_board_scan")

        # Analyze previously recorded snapshots if available
        if self._board_snapshots:
            self._analyze_snapshots()

        if not p:
            return

        # Use OCR to supplement board analysis when no scanner is available
        if self._ocr:
            texts = self._ocr(p)
            self._extract_board_info_from_ocr(texts)

    def _analyze_snapshots(self) -> None:
        """Derive board observations from recorded snapshots."""
        sizes = [s.get("board_size") for s in self._board_snapshots if s.get("board_size")]
        if sizes:
            # Use the most common board size
            most_common_size = max(set(sizes), key=sizes.count)
            self.observe(
                "board_size",
                most_common_size,
                confidence=0.8,
                notes=f"Mode board size from {len(sizes)} snapshots",
            )

        item_counts = [s.get("item_count") for s in self._board_snapshots if s.get("item_count") is not None]
        if item_counts:
            self.observe(
                "item_count",
                round(sum(item_counts) / len(item_counts), 1),
                confidence=0.75,
                notes=f"Average item count over {len(item_counts)} snapshots",
            )

        all_tiers = []
        for s in self._board_snapshots:
            tiers = s.get("tiers", [])
            if tiers:
                all_tiers.extend(tiers)
        if all_tiers:
            self.observe(
                "highest_tier",
                max(all_tiers),
                confidence=0.8,
                notes=f"Highest tier observed across {len(self._board_snapshots)} snapshots",
            )

        empty_counts = [s.get("empty_cells") for s in self._board_snapshots if s.get("empty_cells") is not None]
        if empty_counts:
            self.observe(
                "empty_cells",
                round(sum(empty_counts) / len(empty_counts), 1),
                confidence=0.7,
                notes=f"Average empty cells over {len(empty_counts)} snapshots",
            )

    def _extract_board_info_from_ocr(self, texts: List[Tuple]) -> None:
        """Use OCR text to supplement board observations."""
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect tier/level indicators like "Lv.5", "Tier 3", "T4"
        tier_pattern = re.compile(r"(?:tier|lv\.?|t)\s*(\d+)", re.I)
        tiers_found = []
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            for m in tier_pattern.finditer(text):
                try:
                    tiers_found.append(int(m.group(1)))
                except ValueError:
                    continue
        if tiers_found:
            self.observe(
                "highest_tier",
                max(tiers_found),
                confidence=0.55,
                notes=f"Highest tier from OCR pattern scan: {tiers_found}",
            )

        # Detect full board warning keywords
        full_keywords = ["full", "가득", "no space", "공간 없음"]
        if any(kw in all_text for kw in full_keywords):
            self.observe(
                "empty_cells",
                0,
                confidence=0.6,
                notes="Board full indicator detected via OCR keyword",
            )


class MergeOrderObserver(ObserverBase):
    """Observes order system: active orders, required items, completion rate."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(6, "MergeOrder", "content", capture_fn, observations)
        self._ocr = ocr_fn
        self._completed_orders: int = 0
        self._total_orders: int = 0

    def record_order_result(self, completed: bool) -> None:
        """Record an order outcome to track completion rate."""
        self._total_orders += 1
        if completed:
            self._completed_orders += 1

    def run(self) -> None:
        p = self.screenshot("merge_order_scan")

        # Report completion rate from recorded events
        if self._total_orders > 0:
            rate = round(self._completed_orders / self._total_orders, 2)
            self.observe(
                "order_completion_rate",
                rate,
                confidence=0.8,
                notes=f"{self._completed_orders}/{self._total_orders} orders completed",
            )

        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect order UI presence
        order_keywords = ["order", "주문", "deliver", "배달", "request", "요청"]
        order_ui_present = any(kw in all_text for kw in order_keywords)
        self.observe(
            "active_orders",
            order_ui_present,
            confidence=0.6,
            notes="OCR keyword detection for order UI elements",
        )

        # Count order-related keyword occurrences as proxy for active order count
        order_occurrences = sum(
            all_text.count(kw)
            for kw in ["order", "주문", "deliver", "배달"]
        )
        if order_occurrences > 0:
            self.observe(
                "order_ui_keyword_count",
                order_occurrences,
                confidence=0.5,
                notes="Keyword occurrence proxy for number of visible orders",
            )

        # Extract items needed from order UI (e.g. "3/5 items")
        items_needed = self._extract_items_needed(texts)
        if items_needed is not None:
            self.observe(
                "order_items_needed",
                items_needed,
                confidence=0.6,
                notes="Extracted from 'N/M items' progress pattern in OCR",
            )

    def _extract_items_needed(self, texts: List[Tuple]) -> Optional[int]:
        """Extract items still needed from patterns like '2/5' or '3 of 5'."""
        progress_pattern = re.compile(r"(\d+)\s*/\s*(\d+)")
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            m = progress_pattern.search(text)
            if m:
                try:
                    current = int(m.group(1))
                    total = int(m.group(2))
                    return max(0, total - current)
                except ValueError:
                    continue
        return None


class MergeEnergyObserver(ObserverBase):
    """Observes energy system: current/max energy and regen rate."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(7, "MergeEnergy", "balance", capture_fn, observations)
        self._ocr = ocr_fn
        self._energy_samples: List[Tuple[int, int]] = []

    def record_energy_sample(self, current: int, maximum: int) -> None:
        """Record an energy current/max pair for regen rate estimation."""
        self._energy_samples.append((current, maximum))

    def run(self) -> None:
        p = self.screenshot("merge_energy_scan")

        # Derive regen rate from samples if available
        if len(self._energy_samples) >= 2:
            self._estimate_regen_rate()

        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        current, maximum = self._extract_energy_bar(texts)

        if current is not None:
            self.observe(
                "energy_current",
                current,
                confidence=0.75,
                notes="Extracted from 'N/M' energy bar pattern in OCR",
            )
        if maximum is not None:
            self.observe(
                "energy_max",
                maximum,
                confidence=0.8,
                notes="Extracted from 'N/M' energy bar pattern in OCR",
            )

        # Detect energy regen hint text (e.g. "+1/5min", "regen", "충전")
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))
        regen_keywords = ["regen", "recharge", "충전", "recover", "회복", "+1"]
        if any(kw in all_text for kw in regen_keywords):
            regen_rate = self._extract_regen_rate_from_text(texts)
            if regen_rate is not None:
                self.observe(
                    "energy_regen_rate",
                    regen_rate,
                    confidence=0.6,
                    notes="Regen rate extracted from OCR text pattern",
                )

    def _extract_energy_bar(self, texts: List[Tuple]) -> Tuple[Optional[int], Optional[int]]:
        """Extract current and max energy from 'N/M' bar patterns in OCR text."""
        bar_pattern = re.compile(r"(\d+)\s*/\s*(\d+)")
        energy_context = ["energy", "에너지", "stamina", "스태미나", "ap", "행동력"]
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            if not any(kw in text.lower() for kw in energy_context):
                # Also match standalone N/M pattern for energy-like bars
                m = bar_pattern.search(text)
                if not m:
                    continue
            else:
                m = bar_pattern.search(text)
                if not m:
                    continue
            try:
                return int(m.group(1)), int(m.group(2))
            except ValueError:
                continue
        return None, None

    def _extract_regen_rate_from_text(self, texts: List[Tuple]) -> Optional[float]:
        """Extract regen rate from patterns like '+1/5min' or '1 per 3 minutes'."""
        regen_pattern = re.compile(
            r"\+?\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*(m(?:in(?:ute)?)?s?|h(?:our)?s?)", re.I
        )
        per_pattern = re.compile(
            r"(\d+(?:\.\d+)?)\s*per\s*(\d+(?:\.\d+)?)\s*(m(?:in(?:ute)?)?s?|h(?:our)?s?)", re.I
        )
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            for pattern in (regen_pattern, per_pattern):
                m = pattern.search(text)
                if m:
                    try:
                        amount = float(m.group(1))
                        interval = float(m.group(2))
                        unit = m.group(3).lower()
                        # Normalize to per-minute rate
                        if unit.startswith("h"):
                            interval_minutes = interval * 60
                        else:
                            interval_minutes = interval
                        if interval_minutes > 0:
                            return round(amount / interval_minutes, 4)
                    except ValueError:
                        continue
        return None

    def _estimate_regen_rate(self) -> None:
        """Estimate regen rate from recorded energy samples (requires timestamps in caller)."""
        # Without timestamps we can only report the range
        values = [s[0] for s in self._energy_samples]
        maxes = [s[1] for s in self._energy_samples]
        if maxes:
            self.observe(
                "energy_max",
                max(set(maxes), key=maxes.count),
                confidence=0.8,
                notes=f"Mode energy max from {len(maxes)} samples",
            )
        if len(values) >= 2:
            delta = values[-1] - values[0]
            if delta > 0:
                self.observe(
                    "energy_regen_rate",
                    delta,
                    confidence=0.5,
                    notes=f"Net energy gain across {len(values)} samples (no time normalization)",
                )
