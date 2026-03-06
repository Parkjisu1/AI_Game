"""
Action Pattern -- Behavior Pattern Data Models
================================================
Stores learned action patterns as intent-based sequences, not raw coordinates.

Each step records: screen context -> action intent -> target description -> expected result.
During replay, the executor matches by intent+context, not by exact coordinates.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging
logger = logging.getLogger(__name__)


@dataclass
class ActionStep:
    """Single step in a learned action pattern.

    Intent-based: describes WHAT to do, not WHERE to tap.
    Coordinates stored as fallback only.
    """
    # Context: when does this step apply?
    screen_type: str                # screen_type when action is taken
    ocr_context: List[str] = field(default_factory=list)  # visible text keywords

    # Intent: what are we trying to do?
    intent: str = ""                # "navigate", "tap_button", "select_item",
                                    # "scroll", "close", "confirm", "equip", "enhance"
    target_desc: str = ""           # human-readable: "HP potion", "upgrade button"

    # Target matching (semantic, not coordinate-based)
    target_element: str = ""        # nav_graph element name if matched
    target_text: str = ""           # OCR text to search for (primary match method)
    target_region: str = ""         # "top", "center", "bottom", "left", "right"

    # Action details
    action_type: str = "tap"        # "tap", "swipe", "scroll_down", "scroll_up", "back"
    swipe_direction: str = ""       # "up", "down", "left", "right" (for swipe/scroll)

    # Fallback coordinates (used only when semantic match fails)
    fallback_x: int = 540
    fallback_y: int = 960

    # Expected outcome
    expected_screen: str = ""       # screen_type after action ("" = same screen)
    expected_text: List[str] = field(default_factory=list)  # text that should appear

    # Hierarchical execution support
    screen_type_alternatives: List[str] = field(default_factory=list)  # additional accepted screen types
    sub_pattern: Optional[str] = None      # sub-pattern name to push/execute
    on_fail_pattern: Optional[str] = None  # recovery pattern on step failure
    max_wait_s: float = 3.0                # seconds to wait for expected_screen transition

    # Metadata
    confidence: float = 1.0
    wait_after: float = 1.5         # seconds to wait after this step


@dataclass
class ActionPattern:
    """A complete action flow (e.g., "buy_potion", "complete_quest_1").

    Represents a sequence of behavior steps that achieve a specific goal.
    """
    name: str                       # unique identifier
    category: str                   # "quest", "popup", "upgrade", "shop", "navigation"
    description: str = ""           # human-readable description

    # When to trigger this pattern
    trigger_screen: str = ""        # screen_type that triggers this pattern
    trigger_text: List[str] = field(default_factory=list)  # OCR text that triggers
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)

    # The action sequence
    steps: List[ActionStep] = field(default_factory=list)

    # Success/failure indicators
    success_screen: str = ""        # screen_type when pattern completed
    success_text: List[str] = field(default_factory=list)  # text confirming success

    # Stats
    created_at: str = ""
    use_count: int = 0
    success_count: int = 0
    last_used: str = ""

    @property
    def success_rate(self) -> float:
        if self.use_count == 0:
            return 0.0
        return self.success_count / self.use_count

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["steps"] = [asdict(s) for s in self.steps]
        return d

    @staticmethod
    def from_dict(d: Dict) -> "ActionPattern":
        steps = [ActionStep(**s) for s in d.pop("steps", [])]
        return ActionPattern(steps=steps, **d)


class PatternDB:
    """Persistent storage for learned action patterns.

    Stored as JSON in the game's data directory.
    """

    def __init__(self, db_path: Path):
        self._path = db_path
        self._patterns: Dict[str, ActionPattern] = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                for name, pdata in data.get("patterns", {}).items():
                    self._patterns[name] = ActionPattern.from_dict(pdata)
                logger.info("PatternDB: loaded %d patterns from %s",
                            len(self._patterns), self._path)
            except Exception as e:
                logger.warning("PatternDB: load failed: %s", e)

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "pattern_count": len(self._patterns),
            "patterns": {
                name: p.to_dict() for name, p in self._patterns.items()
            },
        }
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("PatternDB: saved %d patterns to %s",
                     len(self._patterns), self._path)

    def add(self, pattern: ActionPattern):
        self._patterns[pattern.name] = pattern
        self.save()

    def get(self, name: str) -> Optional[ActionPattern]:
        return self._patterns.get(name)

    def get_by_category(self, category: str) -> List[ActionPattern]:
        return [p for p in self._patterns.values() if p.category == category]

    def get_by_trigger(self, screen_type: str, ocr_texts: List[str] = None
                       ) -> List[ActionPattern]:
        """Find patterns that match the current screen context."""
        matches = []
        texts_lower = [t.lower() for t in (ocr_texts or [])]

        for p in self._patterns.values():
            # Screen match
            if p.trigger_screen and p.trigger_screen != screen_type:
                continue

            # Text match (any trigger text found in OCR)
            if p.trigger_text:
                text_matched = any(
                    tt.lower() in " ".join(texts_lower)
                    for tt in p.trigger_text
                )
                if not text_matched:
                    continue

            matches.append(p)

        # Sort by success rate, then use_count
        matches.sort(key=lambda p: (p.success_rate, p.use_count), reverse=True)
        return matches

    def all_patterns(self) -> List[ActionPattern]:
        return list(self._patterns.values())

    def remove(self, name: str) -> bool:
        if name in self._patterns:
            del self._patterns[name]
            self.save()
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._patterns)
