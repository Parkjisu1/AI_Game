"""
SLG Observers -- SLG Genre-Specific Parameter Observers
========================================================
Resource tracking, military status, territory control for SLG games.
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import ObserverBase, ScreenCaptureFn

logger = logging.getLogger(__name__)


class SLGResourceObserver(ObserverBase):
    """Observes top-bar resources: food, wood, stone, iron, gold."""

    # Maps common OCR labels to canonical resource names
    _RESOURCE_ALIASES: Dict[str, List[str]] = {
        "food": ["food", "음식", "grain", "곡물", "wheat", "밀"],
        "wood": ["wood", "나무", "lumber", "목재", "timber"],
        "stone": ["stone", "돌", "rock", "암석", "mineral"],
        "iron": ["iron", "철", "metal", "금속", "ore", "광석"],
        "gold": ["gold", "골드", "coin", "coins", "코인", "silver", "은"],
    }

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(5, "SLGResource", "balance", capture_fn, observations)
        self._ocr = ocr_fn
        self._resource_history: List[Dict[str, float]] = []

    def record_resource_snapshot(self, snapshot: Dict[str, float]) -> None:
        """Record a resource snapshot for trend analysis."""
        self._resource_history.append(snapshot)

    def run(self) -> None:
        p = self.screenshot("slg_resource_scan")

        # Report trends from recorded history
        if len(self._resource_history) >= 2:
            self._report_resource_trends()

        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        resources = self._extract_resources(texts)
        for name, value in resources.items():
            self.observe(
                f"resource_{name}",
                value,
                confidence=0.65,
                notes=f"Extracted from OCR top-bar scan ({name})",
            )
        if resources:
            self.observe(
                "resource_types_visible",
                list(resources.keys()),
                confidence=0.7,
                notes=f"Resources detected in top bar: {list(resources.keys())}",
            )

    def _extract_resources(self, texts: List[Tuple]) -> Dict[str, float]:
        """Match OCR text to resource types and extract numeric values."""
        multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "t": 1_000_000_000_000}
        number_pattern = re.compile(r"([\d,]+\.?\d*)\s*([KkMmBbTt]?)")
        results: Dict[str, float] = {}

        for text, conf, y, x in texts:
            if not isinstance(text, str):
                continue
            text_lower = text.lower()
            matched_resource = None
            for resource, aliases in self._RESOURCE_ALIASES.items():
                if any(alias in text_lower for alias in aliases):
                    matched_resource = resource
                    break
            if not matched_resource:
                continue
            m = number_pattern.search(text)
            if m:
                try:
                    value = float(m.group(1).replace(",", ""))
                    suffix = m.group(2).lower()
                    value *= multipliers.get(suffix, 1)
                    results[matched_resource] = value
                except ValueError:
                    continue
        return results

    def _report_resource_trends(self) -> None:
        """Report income rate for each resource using recorded history snapshots."""
        first = self._resource_history[0]
        last = self._resource_history[-1]
        for resource in self._RESOURCE_ALIASES:
            if resource in first and resource in last:
                delta = last[resource] - first[resource]
                if delta > 0:
                    self.observe(
                        f"resource_{resource}_income",
                        round(delta, 2),
                        confidence=0.6,
                        notes=f"Net gain across {len(self._resource_history)} snapshots",
                    )


class SLGMilitaryObserver(ObserverBase):
    """Observes military state: troop count, troop types, active marches, army power."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(6, "SLGMilitary", "ingame", capture_fn, observations)
        self._ocr = ocr_fn
        self._march_events: List[Dict] = []

    def record_march_event(self, event: Dict) -> None:
        """Record a march event with keys: type, troop_count, destination."""
        self._march_events.append(event)

    def run(self) -> None:
        p = self.screenshot("slg_military_scan")

        # Report active march count from recorded events
        if self._march_events:
            self.observe(
                "active_marches",
                len(self._march_events),
                confidence=0.8,
                notes=f"Recorded {len(self._march_events)} march events",
            )
            troop_totals = [e.get("troop_count", 0) for e in self._march_events]
            if any(t > 0 for t in troop_totals):
                self.observe(
                    "troop_count",
                    max(troop_totals),
                    confidence=0.7,
                    notes=f"Max troop count from {len(self._march_events)} recorded marches",
                )

        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect march/troop UI presence
        march_keywords = ["march", "행군", "troop", "troops", "병사", "army", "군대"]
        march_present = any(kw in all_text for kw in march_keywords)
        self.observe(
            "military_ui_present",
            march_present,
            confidence=0.6,
            notes="OCR keyword detection for military / march UI",
        )

        # Extract army power value (e.g. "Power: 12,500", "전투력 8,000")
        power = self._extract_army_power(texts)
        if power is not None:
            self.observe(
                "army_power",
                power,
                confidence=0.65,
                notes="Army power extracted from OCR",
            )

        # Detect troop types from text
        troop_types = self._detect_troop_types(all_text)
        if troop_types:
            self.observe(
                "troop_types",
                troop_types,
                confidence=0.6,
                notes=f"Troop type keywords detected: {troop_types}",
            )

        # Extract active march count from "N/M" march slot patterns
        march_count = self._extract_march_count(texts)
        if march_count is not None:
            self.observe(
                "active_marches",
                march_count,
                confidence=0.65,
                notes="Active marches extracted from march slot pattern",
            )

    def _extract_army_power(self, texts: List[Tuple]) -> Optional[float]:
        """Extract army power from patterns like 'Power: 12,500' or '전투력 8K'."""
        power_keywords = ["power", "전투력", "combat", "might", "전력"]
        multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
        number_pattern = re.compile(r"([\d,]+\.?\d*)\s*([KkMmBb]?)")
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            if not any(kw in text.lower() for kw in power_keywords):
                continue
            m = number_pattern.search(text)
            if m:
                try:
                    value = float(m.group(1).replace(",", ""))
                    suffix = m.group(2).lower()
                    value *= multipliers.get(suffix, 1)
                    return value
                except ValueError:
                    continue
        return None

    def _detect_troop_types(self, all_text: str) -> List[str]:
        """Identify troop types mentioned in combined OCR text."""
        type_keywords = {
            "infantry": ["infantry", "보병", "soldier", "warrior"],
            "cavalry": ["cavalry", "기병", "horse", "rider"],
            "archer": ["archer", "궁수", "ranged", "bowman"],
            "siege": ["siege", "공성", "catapult", "trebuchet"],
            "mage": ["mage", "마법사", "wizard", "sorcerer"],
        }
        found = []
        for troop_type, keywords in type_keywords.items():
            if any(kw in all_text for kw in keywords):
                found.append(troop_type)
        return found

    def _extract_march_count(self, texts: List[Tuple]) -> Optional[int]:
        """Extract active march count from 'N/M' slot patterns near march keywords."""
        progress_pattern = re.compile(r"(\d+)\s*/\s*(\d+)")
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            if not any(kw in text.lower() for kw in ["march", "행군", "queue", "대기"]):
                continue
            m = progress_pattern.search(text)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
        return None


class SLGTerritoryObserver(ObserverBase):
    """Observes territory control: territory count, alliance size, castle level."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(7, "SLGTerritory", "content", capture_fn, observations)
        self._ocr = ocr_fn
        self._territory_snapshots: List[Dict] = []

    def record_territory_snapshot(self, snapshot: Dict) -> None:
        """Record a territory snapshot with keys: territory_count, alliance_size, castle_level."""
        self._territory_snapshots.append(snapshot)

    def run(self) -> None:
        p = self.screenshot("slg_territory_scan")

        # Report from recorded snapshots
        if self._territory_snapshots:
            self._analyze_territory_snapshots()

        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))

        # Detect territory/map UI presence
        territory_keywords = ["territory", "영토", "region", "지역", "zone", "구역"]
        territory_ui = any(kw in all_text for kw in territory_keywords)
        self.observe(
            "territory_ui_present",
            territory_ui,
            confidence=0.6,
            notes="OCR keyword detection for territory/map UI",
        )

        # Extract castle level
        castle_level = self._extract_castle_level(texts)
        if castle_level is not None:
            self.observe(
                "castle_level",
                castle_level,
                confidence=0.7,
                notes="Castle level extracted from OCR",
            )

        # Detect alliance info
        alliance_keywords = ["alliance", "동맹", "guild", "clan", "클랜"]
        alliance_present = any(kw in all_text for kw in alliance_keywords)
        self.observe(
            "alliance_detected",
            alliance_present,
            confidence=0.6,
            notes="OCR keyword detection for alliance/guild UI element",
        )

        # Extract alliance/member size count
        alliance_size = self._extract_alliance_size(texts)
        if alliance_size is not None:
            self.observe(
                "alliance_size",
                alliance_size,
                confidence=0.6,
                notes="Alliance member count extracted from OCR",
            )

        # Extract territory count
        territory_count = self._extract_territory_count(texts)
        if territory_count is not None:
            self.observe(
                "territory_count",
                territory_count,
                confidence=0.55,
                notes="Territory count extracted from OCR",
            )

    def _extract_castle_level(self, texts: List[Tuple]) -> Optional[int]:
        """Extract castle/city hall level from patterns like 'Castle Lv.10' or '성 레벨 7'."""
        castle_pattern = re.compile(
            r"(?:castle|city\s*hall|headquarters|성|본성|성채)\s*(?:lv\.?|level|레벨)?\s*\.?\s*(\d+)",
            re.I,
        )
        level_near_castle = re.compile(r"(?:lv\.?|level|레벨)\s*\.?\s*(\d+)", re.I)
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            m = castle_pattern.search(text)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
            # If text contains a castle keyword, extract the first level number nearby
            if any(kw in text.lower() for kw in ["castle", "성", "city hall", "headquarters"]):
                m2 = level_near_castle.search(text)
                if m2:
                    try:
                        return int(m2.group(1))
                    except ValueError:
                        continue
        return None

    def _extract_alliance_size(self, texts: List[Tuple]) -> Optional[int]:
        """Extract alliance member count from patterns like 'Members: 45' or '동맹원 30명'."""
        member_pattern = re.compile(r"(?:member|멤버|동맹원|인원)[^\d]*(\d+)", re.I)
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            m = member_pattern.search(text)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
        return None

    def _extract_territory_count(self, texts: List[Tuple]) -> Optional[int]:
        """Extract territory count from patterns like 'Territory: 12' or '영토 5개'."""
        territory_pattern = re.compile(r"(?:territory|territories|영토)[^\d]*(\d+)", re.I)
        for text, _, _, _ in texts:
            if not isinstance(text, str):
                continue
            m = territory_pattern.search(text)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
        return None

    def _analyze_territory_snapshots(self) -> None:
        """Derive observations from recorded territory snapshots."""
        t_counts = [
            s.get("territory_count")
            for s in self._territory_snapshots
            if s.get("territory_count") is not None
        ]
        if t_counts:
            self.observe(
                "territory_count",
                max(t_counts),
                confidence=0.8,
                notes=f"Max territory count from {len(t_counts)} snapshots",
            )

        a_sizes = [
            s.get("alliance_size")
            for s in self._territory_snapshots
            if s.get("alliance_size") is not None
        ]
        if a_sizes:
            self.observe(
                "alliance_size",
                max(set(a_sizes), key=a_sizes.count),
                confidence=0.75,
                notes=f"Mode alliance size from {len(a_sizes)} snapshots",
            )

        c_levels = [
            s.get("castle_level")
            for s in self._territory_snapshots
            if s.get("castle_level") is not None
        ]
        if c_levels:
            self.observe(
                "castle_level",
                max(c_levels),
                confidence=0.8,
                notes=f"Max castle level from {len(c_levels)} snapshots",
            )
