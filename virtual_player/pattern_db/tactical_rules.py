"""
Tactical Rules (L1)
====================
screen_type -> action_sequence mapping.
Uses nav_graph BFS for path-based decisions.
Target: <200ms per decision.

This layer handles:
- Navigation between known screens (BFS pathfinding)
- Common game patterns (e.g. "at lobby, goal is battle" -> tap specific button)
- Sequence plans (multi-step navigation)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..navigation.nav_graph import NavigationGraph, NavEdge, NavAction


@dataclass
class ActionSequence:
    """A planned sequence of actions to achieve a goal."""
    goal: str                           # Target screen or objective
    steps: List[NavEdge] = field(default_factory=list)
    current_step: int = 0

    @property
    def is_complete(self) -> bool:
        return self.current_step >= len(self.steps)

    @property
    def next_edge(self) -> Optional[NavEdge]:
        if self.is_complete:
            return None
        return self.steps[self.current_step]

    def advance(self):
        """Mark current step as done, move to next."""
        self.current_step += 1


@dataclass
class GameObjective:
    """A high-level game objective with priority."""
    name: str                   # e.g. "explore_shop", "complete_daily"
    target_screens: List[str]   # Screens to visit
    priority: int = 0           # Higher = more important
    completed: bool = False


class TacticalRules:
    """L1 tactical decision layer using nav_graph pathfinding.

    Given a current screen and a goal, plans and returns the next action.
    Does NOT call Vision API -- pure graph computation.
    """

    def __init__(self, graph: NavigationGraph, cache_dir: Path):
        self.graph = graph
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Current planned sequence
        self._current_plan: Optional[ActionSequence] = None
        # Objectives queue
        self._objectives: List[GameObjective] = []
        # Screen type -> common actions learned from successful navigations
        self._learned_patterns: Dict[str, List[dict]] = {}
        self._patterns_file = cache_dir / "tactical_patterns.json"
        self._load_patterns()
        # Failed edges: (source, target, element) tuples to skip during planning
        self._failed_edges: set = set()

    def plan_navigation(self, current_screen: str, target: str,
                        equivalences: Dict[str, str] = None) -> Optional[ActionSequence]:
        """Plan a navigation path from current screen to target.

        Returns ActionSequence if path found, None if unreachable.
        This is pure BFS -- no API calls, <200ms.
        Excludes failed edges from pathfinding.
        """
        equivalences = equivalences or {}

        # Check equivalence
        if current_screen == target:
            return ActionSequence(goal=target, steps=[], current_step=0)
        base_curr = equivalences.get(current_screen, current_screen)
        base_tgt = equivalences.get(target, target)
        if base_curr == base_tgt:
            return ActionSequence(goal=target, steps=[], current_step=0)

        # BFS path (excluding failed edges)
        path = self.graph.find_path(
            current_screen, target, excluded_edges=self._failed_edges
        )
        if path is not None:
            plan = ActionSequence(goal=target, steps=path)
            self._current_plan = plan
            return plan

        return None

    def get_next_action(self, current_screen: str, target: str,
                        equivalences: Dict[str, str] = None) -> Optional[NavEdge]:
        """Get the next action edge for reaching the target.

        Uses cached plan if available and still valid.
        Returns NavEdge to execute, or None if no path.
        Skips edges marked as failed.
        """
        equivalences = equivalences or {}

        # Check if current plan is still valid
        if (self._current_plan
                and self._current_plan.goal == target
                and not self._current_plan.is_complete):
            next_edge = self._current_plan.next_edge
            if next_edge and next_edge.source == current_screen:
                key = (next_edge.source, next_edge.target, next_edge.action.element)
                if key not in self._failed_edges:
                    return next_edge
                # Edge is marked as failed -- re-plan excluding it
                self._current_plan = None

        # Re-plan
        plan = self.plan_navigation(current_screen, target, equivalences)
        if plan and not plan.is_complete:
            next_edge = plan.next_edge
            if next_edge:
                key = (next_edge.source, next_edge.target, next_edge.action.element)
                if key not in self._failed_edges:
                    return next_edge
        return None

    def advance_plan(self):
        """Mark current plan step as done."""
        if self._current_plan:
            self._current_plan.advance()

    def mark_edge_failed(self, edge: NavEdge):
        """Mark a specific edge as failed so it won't be retried."""
        key = (edge.source, edge.target, edge.action.element)
        self._failed_edges.add(key)

    def clear_plan(self):
        """Invalidate the current plan (e.g. after stuck detection)."""
        self._current_plan = None

    def set_objectives(self, objectives: List[GameObjective]):
        """Set the list of game objectives (sorted by priority)."""
        self._objectives = sorted(objectives, key=lambda o: o.priority, reverse=True)

    def get_current_objective(self) -> Optional[GameObjective]:
        """Get the highest-priority incomplete objective."""
        for obj in self._objectives:
            if not obj.completed:
                return obj
        return None

    def learn_pattern(self, screen_type: str, action: dict, success: bool):
        """Record a successful navigation pattern for future L1 lookup."""
        if not success:
            return
        if screen_type not in self._learned_patterns:
            self._learned_patterns[screen_type] = []
        # Avoid duplicates
        for existing in self._learned_patterns[screen_type]:
            if (existing.get("action_type") == action.get("action_type")
                    and abs(existing.get("x", 0) - action.get("x", 0)) < 50
                    and abs(existing.get("y", 0) - action.get("y", 0)) < 50):
                existing["count"] = existing.get("count", 1) + 1
                return
        action["count"] = 1
        self._learned_patterns[screen_type].append(action)

    def get_learned_action(self, screen_type: str, target: str) -> Optional[dict]:
        """Get a previously learned action for this screen->target transition."""
        patterns = self._learned_patterns.get(screen_type, [])
        for p in sorted(patterns, key=lambda x: x.get("count", 0), reverse=True):
            if p.get("target") == target:
                return p
        return None

    def save(self):
        """Persist learned patterns to disk."""
        self._patterns_file.write_text(
            json.dumps(self._learned_patterns, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_patterns(self):
        """Load learned patterns from disk."""
        if not self._patterns_file.exists():
            return
        try:
            self._learned_patterns = json.loads(
                self._patterns_file.read_text(encoding="utf-8")
            )
        except Exception:
            pass
