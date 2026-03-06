"""
Idle Observers -- Idle Genre-Specific Parameter Observers
==========================================================
Resource accumulation, upgrade tracking, automation state for Idle games.
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import ObserverBase, ScreenCaptureFn

logger = logging.getLogger(__name__)


class IdleProgressObserver(ObserverBase):
    """Observes idle progress: offline rewards, resource rates, prestige availability."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(5, "IdleProgress", "ingame", capture_fn, observations)
        self._ocr = ocr_fn

    def run(self) -> None:
        p = self.screenshot("idle_progress_scan")
        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect offline reward popup
        offline_keywords = ["offline", "보상", "while you were away", "오프라인"]
        offline_available = any(kw in all_text for kw in offline_keywords)
        self.observe(
            "offline_reward_available",
            offline_available,
            confidence=0.7,
            notes="OCR keyword detection for offline reward popup",
        )

        # Extract resource rate (e.g. "1.2K/s", "500/s", "3.4M/s")
        rate = self._extract_resource_rate(texts)
        if rate is not None:
            self.observe(
                "resource_rate",
                rate,
                confidence=0.65,
                notes="Extracted from /s pattern in OCR text",
            )

        # Detect prestige availability
        prestige_keywords = ["prestige", "프레스티지", "rebirth", "reset", "ascend", "초월"]
        prestige_available = any(kw in all_text for kw in prestige_keywords)
        self.observe(
            "prestige_available",
            prestige_available,
            confidence=0.6,
            notes="OCR keyword detection for prestige UI element",
        )

    def _extract_resource_rate(self, texts: List[Tuple]) -> Optional[float]:
        """Extract a numeric resource rate from patterns like '1.2K/s' or '500/s'."""
        rate_pattern = re.compile(r"([\d,]+\.?\d*)\s*([KkMmBbTt]?)\s*/\s*s", re.I)
        multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "t": 1_000_000_000_000}
        for text, conf, _, _ in texts:
            if not isinstance(text, str):
                continue
            m = rate_pattern.search(text)
            if m:
                try:
                    value = float(m.group(1).replace(",", ""))
                    suffix = m.group(2).lower()
                    value *= multipliers.get(suffix, 1)
                    return value
                except ValueError:
                    continue
        return None


class IdleUpgradeObserver(ObserverBase):
    """Observes upgrade state: upgrade count, cost ratios, max hero level."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(6, "IdleUpgrade", "outgame", capture_fn, observations)
        self._ocr = ocr_fn
        self._upgrade_events: List[Dict] = []

    def record_upgrade_event(self, event: Dict) -> None:
        """Record an observed upgrade event for later analysis."""
        self._upgrade_events.append(event)

    def run(self) -> None:
        p = self.screenshot("idle_upgrade_scan")
        if not p or not self._ocr:
            # Fall back to recorded events if no live capture possible
            if self._upgrade_events:
                self._analyze_upgrade_events()
            return

        texts = self._ocr(p)
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect upgrade UI presence
        upgrade_keywords = ["upgrade", "강화", "level up", "레벨업", "cost", "비용"]
        upgrade_ui_present = any(kw in all_text for kw in upgrade_keywords)
        self.observe(
            "upgrade_ui_present",
            upgrade_ui_present,
            confidence=0.6,
            notes="OCR keyword detection for upgrade interface",
        )

        # Extract level numbers
        levels = self._extract_levels(texts)
        if levels:
            self.observe(
                "max_hero_level",
                max(levels),
                confidence=0.6,
                notes=f"Highest level number found in OCR: {levels}",
            )

        # Extract costs
        costs = self._extract_costs(texts)
        if costs:
            self.observe(
                "upgrade_cost_ratio",
                round(max(costs) / min(costs), 2) if min(costs) > 0 else 1.0,
                confidence=0.5,
                notes=f"Cost range ratio from {len(costs)} values detected",
            )

        # Count visible upgrade buttons / items
        upgrade_count = all_text.count("upgrade") + all_text.count("강화")
        if upgrade_count > 0:
            self.observe(
                "upgrade_count",
                upgrade_count,
                confidence=0.5,
                notes="Keyword occurrence count as proxy for upgrade item count",
            )

        if self._upgrade_events:
            self._analyze_upgrade_events()

    def _extract_levels(self, texts: List[Tuple]) -> List[int]:
        """Extract integer level numbers from OCR text."""
        level_pattern = re.compile(r"(?:lv\.?|level|레벨)\s*\.?\s*(\d+)", re.I)
        levels = []
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            for m in level_pattern.finditer(text):
                try:
                    levels.append(int(m.group(1)))
                except ValueError:
                    continue
        return levels

    def _extract_costs(self, texts: List[Tuple]) -> List[float]:
        """Extract numeric cost values from OCR text."""
        cost_pattern = re.compile(r"([\d,]+\.?\d*)\s*([KkMmBbTt]?)")
        multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "t": 1_000_000_000_000}
        costs = []
        cost_context_keywords = ["cost", "비용", "upgrade", "강화"]
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            if not any(kw in text.lower() for kw in cost_context_keywords):
                continue
            for m in cost_pattern.finditer(text):
                try:
                    value = float(m.group(1).replace(",", ""))
                    suffix = m.group(2).lower()
                    value *= multipliers.get(suffix, 1)
                    if value > 0:
                        costs.append(value)
                except ValueError:
                    continue
        return costs

    def _analyze_upgrade_events(self) -> None:
        """Derive observations from recorded upgrade events."""
        count = len(self._upgrade_events)
        self.observe(
            "upgrade_count",
            count,
            confidence=0.7,
            notes=f"Recorded {count} upgrade events",
        )
        levels = [e.get("level") for e in self._upgrade_events if e.get("level") is not None]
        if levels:
            self.observe(
                "max_hero_level",
                max(levels),
                confidence=0.75,
                notes=f"Max level from {len(levels)} recorded upgrades",
            )


class IdleAutomationObserver(ObserverBase):
    """Observes automation features: auto-mode, speed multipliers, idle duration."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(7, "IdleAutomation", "ingame", capture_fn, observations)
        self._ocr = ocr_fn
        self._session_start_ts: Optional[str] = None

    def record_session_start(self, timestamp: str) -> None:
        """Record the session start timestamp for idle duration calculation."""
        self._session_start_ts = timestamp

    def run(self) -> None:
        p = self.screenshot("idle_automation_scan")
        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect auto mode toggle
        auto_keywords = ["auto", "자동", "automatic"]
        auto_enabled = any(kw in all_text for kw in auto_keywords)
        self.observe(
            "auto_enabled",
            auto_enabled,
            confidence=0.65,
            notes="OCR keyword detection for auto/자동 toggle",
        )

        # Extract speed multiplier (e.g. "x2", "x4", "2x", "4x speed")
        multiplier = self._extract_speed_multiplier(texts)
        if multiplier is not None:
            self.observe(
                "auto_speed_multiplier",
                multiplier,
                confidence=0.7,
                notes=f"Speed multiplier '{multiplier}x' detected in OCR",
            )

        # Detect idle duration hints (e.g. "8h", "2d", "3hours")
        idle_hours = self._extract_idle_duration(texts)
        if idle_hours is not None:
            self.observe(
                "idle_duration_hours",
                idle_hours,
                confidence=0.6,
                notes="Idle/offline duration extracted from time pattern in OCR",
            )

    def _extract_speed_multiplier(self, texts: List[Tuple]) -> Optional[float]:
        """Extract speed multiplier from patterns like 'x2', '4x', '2x speed'."""
        multiplier_pattern = re.compile(r"x\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*x", re.I)
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            if "speed" not in text.lower() and "x" not in text.lower():
                continue
            m = multiplier_pattern.search(text)
            if m:
                raw = m.group(1) or m.group(2)
                try:
                    return float(raw)
                except ValueError:
                    continue
        return None

    def _extract_idle_duration(self, texts: List[Tuple]) -> Optional[float]:
        """Extract idle/offline duration in hours from time patterns like '8h', '2d', '3hours'."""
        hour_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(h(?:our)?s?|시간)", re.I)
        day_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(d(?:ay)?s?|일)", re.I)
        minute_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(m(?:in(?:ute)?)?s?|분)", re.I)

        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            m = day_pattern.search(text)
            if m:
                try:
                    return float(m.group(1)) * 24
                except ValueError:
                    pass
            m = hour_pattern.search(text)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
            m = minute_pattern.search(text)
            if m:
                try:
                    return round(float(m.group(1)) / 60, 3)
                except ValueError:
                    pass
        return None
