"""Quest tracking: OCR text -> parsed objectives -> GOAP action chains."""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .goap_planner import GOAPAction, GOAPGoal

logger = logging.getLogger(__name__)


@dataclass
class QuestObjective:
    """A single quest objective parsed from OCR text."""
    quest_id: str = ""                   # unique ID (auto-generated)
    type: str = "unknown"                # kill, collect, reach, talk, upgrade, clear
    target: str = ""                     # e.g., "몬스터", "stage 2-3", "포션"
    target_count: int = 1                # how many needed
    current_count: int = 0              # current progress
    location: Optional[str] = None      # stage/area if specified
    raw_text: str = ""                  # original OCR text
    completed: bool = False

    @property
    def progress_ratio(self) -> float:
        if self.target_count <= 0:
            return 1.0
        return min(self.current_count / self.target_count, 1.0)


class QuestTracker:
    """Parses quest text, tracks progress, decomposes to GOAP actions."""

    # Korean + English quest patterns
    # Each entry: (regex_pattern, quest_type, default_target)
    PATTERNS = [
        # Kill quests: "몬스터 10마리 처치" (Korean: subject first), "10마리 처치", "Kill 10 monsters"
        (r'(몬스터|적)\s*(\d+)\s*(마리|체|명)?\s*(처치|사냥|kill|defeat)?', 'kill', 'monster'),
        (r'(\d+)\s*(마리|체|명)?\s*(몬스터|적|enemy|monster)\s*(처치|사냥|kill|defeat)?', 'kill', 'monster'),
        (r'(kill|defeat|slay|처치|사냥)\s*(\d+)\s*(monster|enemy|몬스터|적)', 'kill', 'monster'),

        # Collect quests: "포션 5개 수집", "Collect 5 potions"
        (r'(\w+)\s*(\d+)\s*(개|ea)?\s*(수집|collect|모으기|획득)', 'collect', None),
        (r'(collect|gather|수집|획득)\s*(\d+)\s*(\w+)', 'collect', None),

        # Stage/reach quests: "스테이지 2-3 클리어", "Clear stage 2-3"
        (r'스테이지\s*(\d+)[-\s](\d+)', 'reach', 'stage'),
        (r'stage\s*(\d+)[-\s](\d+)', 'reach', 'stage'),
        (r'(클리어|clear)\s*(\d+)[-\s](\d+)', 'clear', 'stage'),

        # Upgrade quests: "장비 강화 3회", "Upgrade equipment 3 times"
        (r'(장비|무기|방어구|equipment|weapon)\s*(강화|upgrade)\s*(\d+)', 'upgrade', 'equipment'),

        # Talk quests: "NPC와 대화", "Talk to merchant"
        (r'(\w+)(와|과|에게)?\s*(대화|talk)', 'talk', None),

        # Generic count: "3회 전투", "Battle 3 times"
        (r'(\d+)\s*(회|번|times)\s*(전투|battle|combat)', 'kill', 'battle'),
    ]

    def __init__(self):
        self._active_quests: Dict[str, QuestObjective] = {}
        self._completed_quests: List[str] = []
        self._quest_counter: int = 0

    def parse_quest_text(self, texts: List[str]) -> List[QuestObjective]:
        """Parse OCR text lines into quest objectives."""
        objectives = []
        for text in texts:
            text_lower = text.lower().strip()
            if len(text_lower) < 3:
                continue

            for pattern, quest_type, default_target in self.PATTERNS:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    obj = self._build_objective(match, quest_type, default_target, text)
                    if obj:
                        objectives.append(obj)
                    break  # first match wins

        # Register new quests (deduplicate by raw text similarity)
        for obj in objectives:
            if obj.quest_id not in self._active_quests:
                self._active_quests[obj.quest_id] = obj
                logger.info(f"New quest: {obj.type} - {obj.target} ({obj.target_count})")

        return objectives

    def _build_objective(
        self,
        match: re.Match,
        quest_type: str,
        default_target: Optional[str],
        raw_text: str,
    ) -> Optional[QuestObjective]:
        """Build QuestObjective from regex match."""
        self._quest_counter += 1
        groups = match.groups()

        # Extract count (first numeric group)
        count = 1
        target = default_target or ""
        location = None

        for g in groups:
            if g and str(g).isdigit():
                count = int(g)
                break

        # Stage location -- extract stage X-Y notation
        if quest_type in ('reach', 'clear'):
            nums = re.findall(r'\d+', match.group())
            if len(nums) >= 2:
                location = f"stage_{nums[0]}_{nums[1]}"
                target = f"stage {nums[0]}-{nums[1]}"

        return QuestObjective(
            quest_id=f"quest_{self._quest_counter}",
            type=quest_type,
            target=target,
            target_count=count,
            location=location,
            raw_text=raw_text,
        )

    def update_progress(self, texts: List[str]) -> None:
        """Update quest progress from OCR text (look for progress indicators)."""
        for text in texts:
            # Match progress patterns: "3/10", "진행: 3/10"
            progress_match = re.search(r'(\d+)\s*/\s*(\d+)', text)
            if progress_match:
                current = int(progress_match.group(1))
                total = int(progress_match.group(2))
                # Find matching active quest by target count
                for quest in self._active_quests.values():
                    if quest.target_count == total and not quest.completed:
                        quest.current_count = current
                        if current >= total:
                            quest.completed = True
                            self._completed_quests.append(quest.quest_id)
                            logger.info(f"Quest completed: {quest.quest_id}")
                        break

            # Check for completion keywords
            if any(kw in text.lower() for kw in ['완료', 'complete', 'clear', '클리어']):
                # Mark most recent uncompleted quest as done
                for quest in self._active_quests.values():
                    if not quest.completed:
                        quest.completed = True
                        self._completed_quests.append(quest.quest_id)
                        logger.info(f"Quest completed by keyword: {quest.quest_id}")
                        break

    def get_active_quests(self) -> List[QuestObjective]:
        """Return uncompleted quests sorted by quest_id (oldest first)."""
        return [q for q in self._active_quests.values() if not q.completed]

    def get_highest_priority_quest(self) -> Optional[QuestObjective]:
        """Return the first uncompleted quest (oldest, lowest completion ratio last)."""
        active = self.get_active_quests()
        if not active:
            return None
        # Prefer nearly-complete quests first
        active.sort(key=lambda q: -q.progress_ratio)
        return active[0]

    def decompose_to_actions(self, objective: QuestObjective) -> List[GOAPAction]:
        """Convert a quest objective into a chain of GOAP actions."""
        actions: List[GOAPAction] = []

        if objective.type == 'kill':
            if objective.location:
                actions.append(GOAPAction(
                    name=f"navigate_to_{objective.location}",
                    cost=2.0,
                    preconditions={},
                    effects={"screen_type": "battle"},
                    required_screen=None,
                    metadata={"type": "navigate", "target": objective.location},
                ))
            actions.append(GOAPAction(
                name="grind_battle",
                cost=1.0,
                preconditions={"screen_type": lambda s: s in (None, "stage_select", "lobby", "loading", "battle")},
                effects={"quest_kill_progress": lambda v: (v or 0) + 1},
                required_screen="stage_select",
                metadata={"type": "combat", "quest_id": objective.quest_id},
            ))

        elif objective.type == 'collect':
            actions.append(GOAPAction(
                name=f"collect_{objective.target}",
                cost=2.0,
                preconditions={},
                effects={"quest_collect_progress": lambda v: (v or 0) + 1},
                metadata={"type": "collect", "target": objective.target},
            ))

        elif objective.type in ('reach', 'clear'):
            actions.append(GOAPAction(
                name="navigate_stage_select",
                cost=1.0,
                preconditions={},
                effects={"screen_type": "stage_select"},
                metadata={"type": "navigate"},
            ))
            actions.append(GOAPAction(
                name=f"select_{objective.location or 'stage'}",
                cost=1.0,
                preconditions={"screen_type": "stage_select"},
                effects={"screen_type": "battle"},
                metadata={"type": "select_stage", "target": objective.location},
            ))
            actions.append(GOAPAction(
                name="clear_stage",
                cost=3.0,
                preconditions={"screen_type": "battle"},
                effects={"quest_clear_progress": lambda v: (v or 0) + 1},
                required_screen="battle",
                metadata={"type": "combat"},
            ))

        elif objective.type == 'upgrade':
            actions.append(GOAPAction(
                name="open_equipment",
                cost=1.0,
                preconditions={},
                effects={"screen_type": "menu_equipment"},
                metadata={"type": "navigate"},
            ))
            actions.append(GOAPAction(
                name="upgrade_equipment",
                cost=2.0,
                preconditions={"screen_type": "menu_equipment"},
                effects={"quest_upgrade_progress": lambda v: (v or 0) + 1},
                metadata={"type": "upgrade"},
            ))

        elif objective.type == 'talk':
            actions.append(GOAPAction(
                name=f"talk_to_{objective.target or 'npc'}",
                cost=1.0,
                preconditions={},
                effects={"quest_talk_done": True},
                metadata={"type": "interact", "target": objective.target},
            ))

        return actions

    def get_quest_goal(self, objective: QuestObjective) -> Optional[GOAPGoal]:
        """Create a GOAP goal for completing a quest objective."""
        if objective.completed:
            return None

        goal_conditions: Dict = {}

        if objective.type == 'kill':
            needed = objective.target_count
            goal_conditions["quest_kill_progress"] = lambda v, n=needed: (v or 0) >= n
        elif objective.type == 'collect':
            needed = objective.target_count
            goal_conditions["quest_collect_progress"] = lambda v, n=needed: (v or 0) >= n
        elif objective.type in ('reach', 'clear'):
            needed = objective.target_count
            goal_conditions["quest_clear_progress"] = lambda v, n=needed: (v or 0) >= n
        elif objective.type == 'upgrade':
            needed = objective.target_count
            goal_conditions["quest_upgrade_progress"] = lambda v, n=needed: (v or 0) >= n
        elif objective.type == 'talk':
            goal_conditions["quest_talk_done"] = True

        if not goal_conditions:
            return None

        return GOAPGoal(
            name=f"complete_{objective.quest_id}",
            conditions=goal_conditions,
            priority=5.0,  # quests are medium priority
        )

    @property
    def has_active_quests(self) -> bool:
        return any(not q.completed for q in self._active_quests.values())

    def reset(self) -> None:
        """Clear all quest state (e.g., on game restart)."""
        self._active_quests.clear()
        self._completed_quests.clear()
        self._quest_counter = 0
