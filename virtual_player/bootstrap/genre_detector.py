"""
GenreDetector -- Auto-Detect Game Genre from UI Patterns
========================================================
Uses UI patterns, OCR keywords, screen count, and navigation complexity
to classify a game's genre via weighted voting.
"""

import logging
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Genre detection signals with weights
GENRE_SIGNALS = {
    "rpg": {
        "ui_patterns": ["hp_bar", "mp_bar", "exp_bar", "minimap", "character_portrait"],
        "ocr_keywords": [
            "hp", "mp", "exp", "level", "quest", "skill", "inventory", "equip",
            "attack", "defense", "strength", "체력", "마력", "경험치", "레벨",
            "퀘스트", "스킬", "인벤", "장비", "공격", "방어",
        ],
        "min_screens": 5,
        "nav_complexity": "high",
    },
    "idle": {
        "ui_patterns": ["progress_bar", "auto_button", "offline_reward", "prestige"],
        "ocr_keywords": [
            "idle", "auto", "offline", "prestige", "reset", "upgrade",
            "per second", "/s", "방치", "자동", "오프라인", "보상", "강화",
            "초당", "생산",
        ],
        "min_screens": 3,
        "nav_complexity": "low",
    },
    "puzzle": {
        "ui_patterns": ["board_grid", "holder_bar", "score_display", "lives_hearts"],
        "ocr_keywords": [
            "score", "level", "lives", "moves", "match", "clear", "combo",
            "star", "heart", "점수", "레벨", "라이프", "이동", "매치",
            "클리어", "콤보", "별", "하트",
        ],
        "min_screens": 3,
        "nav_complexity": "low",
    },
    "merge": {
        "ui_patterns": ["merge_grid", "energy_bar", "order_board"],
        "ocr_keywords": [
            "merge", "combine", "drag", "drop", "order", "energy",
            "합치기", "드래그", "주문", "에너지",
        ],
        "min_screens": 3,
        "nav_complexity": "medium",
    },
    "slg": {
        "ui_patterns": ["world_map", "city_view", "troops", "alliance_icon"],
        "ocr_keywords": [
            "alliance", "troops", "march", "scout", "kingdom", "castle",
            "war", "동맹", "부대", "진군", "정찰", "왕국", "성", "전쟁",
        ],
        "min_screens": 6,
        "nav_complexity": "high",
    },
    "tycoon": {
        "ui_patterns": ["revenue_display", "customer_counter", "staff_panel", "upgrade_button"],
        "ocr_keywords": [
            "revenue", "customers", "staff", "hire", "upgrade", "satisfaction",
            "income", "profit", "business", "expand", "manager",
            "수익", "고객", "직원", "고용", "업그레이드", "만족도",
            "수입", "사업", "확장", "매니저",
        ],
        "min_screens": 4,
        "nav_complexity": "medium",
    },
    "simulation": {
        "ui_patterns": ["population_counter", "happiness_bar", "budget_display", "time_controls"],
        "ocr_keywords": [
            "population", "happiness", "budget", "tax", "build", "zone",
            "citizens", "infrastructure", "disaster", "event", "speed",
            "인구", "행복도", "예산", "세금", "건설", "구역",
            "시민", "인프라", "재난", "이벤트", "속도",
        ],
        "min_screens": 4,
        "nav_complexity": "high",
    },
    "casual": {
        "ui_patterns": ["lives_hearts", "score_display", "level_map", "booster_bar"],
        "ocr_keywords": [
            "lives", "score", "level", "star", "booster", "daily", "reward",
            "heart", "coin", "play", "retry", "bonus", "spin",
            "라이프", "점수", "레벨", "별", "부스터", "일일",
            "보상", "하트", "코인", "시작", "다시", "보너스",
        ],
        "min_screens": 3,
        "nav_complexity": "low",
    },
}


class GenreDetector:
    """Detects game genre from DiscoveryDB data and OCR analysis."""

    # Weights for each signal type
    UI_PATTERN_WEIGHT = 3
    OCR_KEYWORD_WEIGHT = 2
    SCREEN_COUNT_WEIGHT = 1
    NAV_COMPLEXITY_WEIGHT = 1

    def __init__(self, custom_signals: Optional[Dict[str, Dict]] = None):
        """
        Args:
            custom_signals: Override or extend GENRE_SIGNALS.
        """
        self.signals = dict(GENRE_SIGNALS)
        if custom_signals:
            self.signals.update(custom_signals)

    def detect(
        self,
        discovery_data: Dict[str, Any],
        ocr_texts: Optional[List[str]] = None,
        screen_labels: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Dict[str, float]]:
        """
        Detect genre from exploration data.

        Args:
            discovery_data: DiscoveryDB.to_dict() output.
            ocr_texts: All OCR text collected during exploration.
            screen_labels: {screen_name: label_from_fingerprinter}.

        Returns:
            (detected_genre, {genre: confidence_score})
        """
        scores: Dict[str, float] = {genre: 0.0 for genre in self.signals}

        screens = discovery_data.get("screens", {})
        transitions = discovery_data.get("transitions", [])
        screen_count = len(screens)

        # 1. OCR Keyword matching
        if ocr_texts:
            all_text_lower = " ".join(ocr_texts).lower()
            for genre, config in self.signals.items():
                keyword_hits = sum(
                    1 for kw in config["ocr_keywords"]
                    if kw.lower() in all_text_lower
                )
                scores[genre] += keyword_hits * self.OCR_KEYWORD_WEIGHT

        # 2. Screen count heuristic
        for genre, config in self.signals.items():
            min_screens = config.get("min_screens", 3)
            if screen_count >= min_screens:
                scores[genre] += self.SCREEN_COUNT_WEIGHT

        # 3. Navigation complexity
        nav_complexity = self._assess_nav_complexity(transitions, screen_count)
        for genre, config in self.signals.items():
            expected = config.get("nav_complexity", "medium")
            if nav_complexity == expected:
                scores[genre] += self.NAV_COMPLEXITY_WEIGHT

        # 4. UI pattern matching (from screen labels/elements)
        if screen_labels:
            all_labels = " ".join(screen_labels.values()).lower()
            for genre, config in self.signals.items():
                pattern_hits = sum(
                    1 for p in config["ui_patterns"]
                    if p.replace("_", " ") in all_labels or p in all_labels
                )
                scores[genre] += pattern_hits * self.UI_PATTERN_WEIGHT

        # Also check element labels in DiscoveryDB
        all_element_text = ""
        for sdata in screens.values():
            for elem in sdata.get("elements", []):
                all_element_text += " " + elem.get("label", "")
                all_element_text += " " + elem.get("ocr_text", "")
        all_element_text = all_element_text.lower()

        for genre, config in self.signals.items():
            for kw in config["ocr_keywords"]:
                if kw.lower() in all_element_text:
                    scores[genre] += 1  # Lighter weight for element text

        # Normalize scores
        max_score = max(scores.values()) if scores else 1
        if max_score > 0:
            normalized = {g: round(s / max_score, 3) for g, s in scores.items()}
        else:
            normalized = scores

        best_genre = max(scores, key=scores.get)
        logger.info(
            "Genre detection: %s (scores: %s)",
            best_genre, {g: round(s, 1) for g, s in scores.items()},
        )
        return best_genre, normalized

    def _assess_nav_complexity(
        self, transitions: List[Dict], screen_count: int,
    ) -> str:
        """Classify navigation complexity as low/medium/high."""
        edge_count = len(transitions)
        if screen_count <= 3 and edge_count <= 4:
            return "low"
        elif screen_count >= 6 or edge_count >= 10:
            return "high"
        return "medium"
