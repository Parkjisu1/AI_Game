"""
Goal Reasoner — Main Reasoning Orchestrator
============================================
Coordinates interrupt checks → utility scoring → GOAP planning
each tick to produce the next best GOAPAction for the agent.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..adb import log
from .goap_planner import GOAPAction, GOAPGoal, GOAPPlan, GOAPPlanner, WorldState
from .utility_scorer import UtilityScorer


@dataclass
class InterruptRule:
    """Emergency override rule — fires when condition is met, forcing a specific goal."""
    name: str
    condition: Callable[[WorldState], bool]  # when to trigger
    goal_name: str                            # which goal to force
    priority: float = 100.0                   # always wins


class GoalReasoner:
    """Main reasoning orchestrator: interrupt check → utility scoring → GOAP planning."""

    def __init__(
        self,
        planner: GOAPPlanner,
        scorer: UtilityScorer,
        goals: Dict[str, GOAPGoal],
        interrupts: Optional[List[InterruptRule]] = None,
    ):
        self._planner = planner
        self._scorer = scorer
        self._goals = goals  # name -> GOAPGoal
        self._interrupts: List[InterruptRule] = interrupts or []
        self._current_plan: Optional[GOAPPlan] = None
        self._current_goal_name: Optional[str] = None

    def decide(self, snapshot) -> Optional[GOAPAction]:
        """Main decision flow each tick.

        1. Check interrupt rules (emergency override)
        2. Continue current plan if still valid
        3. Utility score → pick best goal → GOAP plan
        """
        world = WorldState.from_snapshot(snapshot)

        # 1. Check interrupts (emergency override)
        for interrupt in self._interrupts:
            if interrupt.condition(world):
                if self._current_goal_name != interrupt.goal_name:
                    log(f"  [GoalReasoner] INTERRUPT: {interrupt.name} → {interrupt.goal_name}")
                    self._force_goal(interrupt.goal_name, world)
                break

        # 2. If current plan still valid, continue
        if self._current_plan and not self._current_plan.is_complete:
            action = self._current_plan.current_action
            if action and action.is_applicable(world):
                log(
                    f"  [GoalReasoner] Continue plan: {action.name} "
                    f"(step {self._current_plan.current_step + 1}/{len(self._current_plan.actions)})"
                )
                return action
            else:
                log(f"  [GoalReasoner] Plan invalid, replanning")
                self._current_plan = None

        # 3. Utility score → pick best goal → GOAP plan
        best = self._scorer.get_best(world)
        if best:
            goal_name, score = best
            log(f"  [GoalReasoner] Best goal: {goal_name} ({score:.2f})")
            goal = self._goals.get(goal_name)
            if goal and not goal.is_satisfied(world):
                goal.priority = score
                plan = self._planner.plan(world, goal)
                if plan and plan.actions:
                    self._current_plan = plan
                    self._current_goal_name = goal_name
                    log(
                        f"  [GoalReasoner] GOAP plan: "
                        f"{' → '.join(a.name for a in plan.actions)}"
                    )
                    return plan.current_action

        return None

    def advance(self):
        """Advance to next step in current plan (called after action succeeds)."""
        if self._current_plan:
            self._current_plan.advance()
            if self._current_plan.is_complete:
                log(f"  [GoalReasoner] Plan complete: {self._current_goal_name}")
                self._current_plan = None
                self._current_goal_name = None

    def _force_goal(self, goal_name: str, world: WorldState):
        """Force-switch to a specific goal by replanning immediately."""
        goal = self._goals.get(goal_name)
        if goal:
            plan = self._planner.plan(world, goal)
            if plan:
                self._current_plan = plan
                self._current_goal_name = goal_name

    @property
    def current_goal(self) -> Optional[str]:
        return self._current_goal_name

    @property
    def current_plan(self) -> Optional[GOAPPlan]:
        return self._current_plan


def build_reasoner_for_genre(genre: str) -> GoalReasoner:
    """Factory: build a fully configured GoalReasoner for the given genre.

    Loads actions, scorers, goals, and interrupt rules from the goal library
    and wires them into a GoalReasoner ready for use.
    """
    from .goal_library import get_goals_for_genre

    registry = get_goals_for_genre(genre)

    planner = GOAPPlanner(actions=registry["actions"])
    scorer = UtilityScorer(goal_scorers=registry["scorers"])
    goals_map: Dict[str, GOAPGoal] = {g.name: g for g in registry["goals"]}

    interrupt_rules = [
        InterruptRule(
            name=r["name"],
            condition=r["condition"],
            goal_name=r["goal_name"],
            priority=r.get("priority", 100.0),
        )
        for r in registry["interrupts"]
    ]
    # Sort interrupts by priority descending so highest priority fires first
    interrupt_rules.sort(key=lambda r: r.priority, reverse=True)

    return GoalReasoner(
        planner=planner,
        scorer=scorer,
        goals=goals_map,
        interrupts=interrupt_rules,
    )
