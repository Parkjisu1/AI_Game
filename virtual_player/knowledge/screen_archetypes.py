"""
ScreenArchetypes -- Common Screen Patterns Across Games
=======================================================
Defines universal screen archetypes that appear in most mobile games.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class ScreenArchetype:
    """A common screen pattern across mobile games."""
    name: str
    keywords: List[str]
    typical_elements: List[str]
    is_safe: bool = True
    typical_position: str = "any"  # "top", "center", "bottom", "fullscreen"


# Universal screen archetypes
ARCHETYPES = {
    "lobby": ScreenArchetype(
        name="lobby",
        keywords=["play", "start", "시작", "플레이", "main", "home", "홈"],
        typical_elements=["play_button", "settings", "shop_icon", "profile"],
        is_safe=True,
    ),
    "battle": ScreenArchetype(
        name="battle",
        keywords=["hp", "mp", "auto", "skill", "attack", "공격", "스킬"],
        typical_elements=["hp_bar", "auto_button", "skill_icons"],
        is_safe=True,
    ),
    "gameplay": ScreenArchetype(
        name="gameplay",
        keywords=["score", "moves", "time", "combo", "점수", "콤보"],
        typical_elements=["board", "score_display", "timer"],
        is_safe=True,
    ),
    "shop": ScreenArchetype(
        name="shop",
        keywords=["shop", "store", "buy", "purchase", "상점", "구매"],
        typical_elements=["item_list", "price_tags", "buy_button"],
        is_safe=False,
    ),
    "inventory": ScreenArchetype(
        name="inventory",
        keywords=["inventory", "bag", "items", "equip", "인벤", "장비", "가방"],
        typical_elements=["item_grid", "equip_slots", "sort_button"],
        is_safe=True,
    ),
    "popup": ScreenArchetype(
        name="popup",
        keywords=["ok", "confirm", "cancel", "close", "확인", "취소", "닫기"],
        typical_elements=["message", "ok_button", "close_button"],
        is_safe=True,
    ),
    "ad": ScreenArchetype(
        name="ad",
        keywords=["skip", "close", "x", "reward", "install"],
        typical_elements=["close_button", "timer", "cta_button"],
        is_safe=True,
    ),
    "settings": ScreenArchetype(
        name="settings",
        keywords=["settings", "option", "sound", "music", "설정", "옵션", "사운드"],
        typical_elements=["toggles", "sliders", "back_button"],
        is_safe=True,
    ),
    "loading": ScreenArchetype(
        name="loading",
        keywords=["loading", "로딩", "please wait", "tip"],
        typical_elements=["progress_bar", "tip_text"],
        is_safe=True,
    ),
    "result": ScreenArchetype(
        name="result",
        keywords=["victory", "defeat", "clear", "fail", "승리", "패배", "클리어"],
        typical_elements=["stars", "score", "next_button", "retry_button"],
        is_safe=True,
    ),
}


class ScreenArchetypes:
    """Provides screen archetype matching."""

    def __init__(self, custom_archetypes: Dict[str, ScreenArchetype] = None):
        self.archetypes = dict(ARCHETYPES)
        if custom_archetypes:
            self.archetypes.update(custom_archetypes)

    def match(self, ocr_texts: List[str]) -> List[Tuple[str, float]]:
        """
        Match OCR text against archetypes.

        Returns:
            List of (archetype_name, confidence) sorted by confidence desc.
        """
        all_text = " ".join(ocr_texts).lower()
        scores = []

        for name, archetype in self.archetypes.items():
            hits = sum(1 for kw in archetype.keywords if kw.lower() in all_text)
            if hits > 0:
                confidence = min(1.0, hits / max(3, len(archetype.keywords)))
                scores.append((name, round(confidence, 2)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def is_safe(self, screen_type: str) -> bool:
        """Check if a screen type is considered safe for exploration."""
        archetype = self.archetypes.get(screen_type)
        if archetype:
            return archetype.is_safe
        return True  # Unknown screens are assumed safe

    def get_keywords(self, screen_type: str) -> List[str]:
        """Get keywords for a screen type."""
        archetype = self.archetypes.get(screen_type)
        return archetype.keywords if archetype else []
