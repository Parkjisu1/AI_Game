"""
RPG Observers -- RPG Genre-Specific Parameter Observers
========================================================
Combat stats, town structure, quest tracking for RPG games.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import ObserverBase, ScreenCaptureFn

logger = logging.getLogger(__name__)


class CombatObserver(ObserverBase):
    """Observes combat: auto-battle, skill usage, damage patterns."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(5, "CombatAnalyst", "ingame", capture_fn, observations)
        self._ocr = ocr_fn
        self._battle_results: List[Dict] = []

    def record_battle_result(self, result: Dict) -> None:
        """Record a battle result for analysis."""
        self._battle_results.append(result)

    def run(self) -> None:
        p = self.screenshot("combat_scan")
        if not p:
            return

        if self._ocr:
            texts = self._ocr(p)
            stats = self._extract_combat_stats(texts)
            if stats:
                for key, val in stats.items():
                    self.observe(f"combat_{key}", val, confidence=0.6,
                                 notes="OCR extracted from battle screen")

        if self._battle_results:
            win_rate = sum(1 for r in self._battle_results if r.get("won", False))
            total = len(self._battle_results)
            self.observe("battle_win_rate", round(win_rate / total, 2),
                         confidence=0.7,
                         notes=f"{win_rate}/{total} battles won")

            auto_count = sum(1 for r in self._battle_results if r.get("auto_battle", False))
            self.observe("auto_battle_available", auto_count > 0,
                         confidence=0.8,
                         notes=f"Auto battle used in {auto_count}/{total} battles")

    def _extract_combat_stats(self, texts: List[Tuple]) -> Dict[str, Any]:
        """Extract combat-related stats from OCR text."""
        import re
        stats = {}
        for text, conf, _, _ in texts:
            if isinstance(text, str):
                # HP pattern
                hp_match = re.search(r"HP\s*[:\.]?\s*(\d+)", text, re.I)
                if hp_match:
                    stats["hp"] = int(hp_match.group(1))
                # ATK/DEF patterns
                atk_match = re.search(r"(?:ATK|공격력?)\s*[:\.]?\s*(\d+)", text, re.I)
                if atk_match:
                    stats["atk"] = int(atk_match.group(1))
        return stats


class TownObserver(ObserverBase):
    """Observes town/hub: available shops, NPCs, facilities."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(6, "TownAnalyst", "outgame", capture_fn, observations)
        self._ocr = ocr_fn

    def run(self) -> None:
        p = self.screenshot("town_scan")
        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        facilities = self._detect_facilities(texts)
        if facilities:
            self.observe("town_facilities", facilities, confidence=0.6,
                         notes="Detected from OCR keywords")
            self.observe("town_facility_count", len(facilities), confidence=0.6)

    def _detect_facilities(self, texts: List[Tuple]) -> List[str]:
        """Detect town facilities from OCR text."""
        facility_keywords = {
            "shop": ["shop", "상점", "store", "가게"],
            "forge": ["forge", "대장간", "craft", "공방", "제작"],
            "inn": ["inn", "여관", "rest", "휴식"],
            "guild": ["guild", "길드"],
            "arena": ["arena", "투기장", "pvp"],
            "gacha": ["gacha", "가챠", "summon", "소환"],
            "quest": ["quest", "퀘스트", "mission", "미션"],
        }
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))
        found = []
        for facility, keywords in facility_keywords.items():
            if any(kw in all_text for kw in keywords):
                found.append(facility)
        return found


class QuestObserver(ObserverBase):
    """Observes quest system: quest types, rewards, tracking."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[Callable] = None,
    ):
        super().__init__(7, "QuestAnalyst", "content", capture_fn, observations)
        self._ocr = ocr_fn
        self._quest_data: List[Dict] = []

    def record_quest(self, quest: Dict) -> None:
        """Record a quest for analysis."""
        self._quest_data.append(quest)

    def run(self) -> None:
        if self._quest_data:
            quest_types = set(q.get("type", "unknown") for q in self._quest_data)
            self.observe("quest_types", list(quest_types), confidence=0.6,
                         notes=f"From {len(self._quest_data)} quests")

        p = self.screenshot("quest_scan")
        if p and self._ocr:
            texts = self._ocr(p)
            has_quest_system = any(
                any(kw in t[0].lower() for kw in ["quest", "퀘스트", "mission", "미션"])
                for t in texts if isinstance(t, tuple)
            )
            self.observe("quest_system_exists", has_quest_system,
                         confidence=0.7, notes="OCR keyword detection")
