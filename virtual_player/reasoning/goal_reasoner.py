"""
Goal Reasoner -- Main Reasoning Orchestrator
============================================
Coordinates interrupt checks -> utility scoring -> GOAP planning
each tick to produce the next best GOAPAction for the agent.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from ..adb import log
from .goap_planner import GOAPAction, GOAPGoal, GOAPPlan, GOAPPlanner, WorldState
from .utility_scorer import UtilityScorer

if TYPE_CHECKING:
    from .quest_tracker import QuestTracker


@dataclass
class InterruptRule:
    """Emergency override rule -- fires when condition is met, forcing a specific goal."""
    name: str
    condition: Callable[[WorldState], bool]  # when to trigger
    goal_name: str                            # which goal to force
    priority: float = 100.0                   # always wins


class GoalReasoner:
    """Main reasoning orchestrator: interrupt check -> utility scoring -> GOAP planning."""

    GOAL_FAIL_LIMIT = 3     # consecutive failures before blacklisting
    GOAL_BLACKLIST_TICKS = 5  # how long a blacklisted goal stays blocked

    def __init__(
        self,
        planner: GOAPPlanner,
        scorer: UtilityScorer,
        goals: Dict[str, GOAPGoal],
        interrupts: Optional[List[InterruptRule]] = None,
        quest_tracker: Optional["QuestTracker"] = None,
    ):
        self._planner = planner
        self._scorer = scorer
        self._goals = goals  # name -> GOAPGoal
        self._interrupts: List[InterruptRule] = interrupts or []
        self._current_plan: Optional[GOAPPlan] = None
        self._current_goal_name: Optional[str] = None
        # Goal cooldown tracking
        self._goal_fail_count: Dict[str, int] = {}
        self._goal_blacklist: Dict[str, int] = {}  # goal_name -> tick when blacklist expires
        self._tick_counter: int = 0
        # Quest integration
        self._quest_tracker: Optional["QuestTracker"] = quest_tracker

    def decide(self, snapshot) -> Optional[GOAPAction]:
        """Main decision flow each tick.

        1. Check interrupt rules (emergency override)
        2. Continue current plan if still valid
        3. Utility score -> pick best goal (skip blacklisted) -> GOAP plan
        """
        self._tick_counter += 1
        world = WorldState.from_snapshot(snapshot)

        # 1. Check interrupts (emergency override)
        for interrupt in self._interrupts:
            if interrupt.condition(world):
                if self._current_goal_name != interrupt.goal_name:
                    log(f"  [GoalReasoner] INTERRUPT: {interrupt.name} -> {interrupt.goal_name}")
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
                # Track failure for the current goal
                if self._current_goal_name:
                    self._record_goal_failure(self._current_goal_name)
                self._current_plan = None

        # 3. Inject quest goals/actions from QuestTracker (if active quests exist)
        self._inject_quest_goals(world)

        # 4. Utility score -> iterate ranked goals, skip blacklisted
        ranked = self._scorer.evaluate(world)
        for goal_name, score in ranked:
            # Skip blacklisted goals
            if goal_name in self._goal_blacklist:
                if self._tick_counter < self._goal_blacklist[goal_name]:
                    log(f"  [GoalReasoner] Skipping blacklisted goal: {goal_name}")
                    continue
                else:
                    # Blacklist expired
                    del self._goal_blacklist[goal_name]
                    self._goal_fail_count.pop(goal_name, None)

            goal = self._goals.get(goal_name)
            if goal and not goal.is_satisfied(world):
                goal.priority = score
                plan = self._planner.plan(world, goal)
                if plan and plan.actions:
                    self._current_plan = plan
                    self._current_goal_name = goal_name
                    log(
                        f"  [GoalReasoner] Best goal: {goal_name} ({score:.2f})"
                    )
                    log(
                        f"  [GoalReasoner] GOAP plan: "
                        f"{' -> '.join(a.name for a in plan.actions)}"
                    )
                    return plan.current_action
                else:
                    # Plan failed -- record failure
                    self._record_goal_failure(goal_name)

        return None

    def _inject_quest_goals(self, world: WorldState) -> None:
        """Pull active quests from QuestTracker and inject their goals/actions into the planner."""
        if self._quest_tracker is None:
            return
        active = self._quest_tracker.get_active_quests()
        if not active:
            return

        # Inject quest-derived actions into the planner (deduplicate by name)
        existing_action_names = {a.name for a in self._planner._actions}
        for objective in active:
            quest_goal = self._quest_tracker.get_quest_goal(objective)
            if quest_goal is None:
                continue
            # Register goal in the goal map if not yet present
            if quest_goal.name not in self._goals:
                self._goals[quest_goal.name] = quest_goal
                log(f"  [GoalReasoner] Quest goal registered: {quest_goal.name}")
            # Inject actions for this objective
            for action in self._quest_tracker.decompose_to_actions(objective):
                if action.name not in existing_action_names:
                    self._planner.add_action(action)
                    existing_action_names.add(action.name)

        # Update world state to signal quest presence for utility scorers
        if "has_active_quest" not in world.props:
            world.props["has_active_quest"] = True

    def _record_goal_failure(self, goal_name: str) -> None:
        """Track consecutive failures and blacklist after GOAL_FAIL_LIMIT."""
        count = self._goal_fail_count.get(goal_name, 0) + 1
        self._goal_fail_count[goal_name] = count
        if count >= self.GOAL_FAIL_LIMIT:
            expires = self._tick_counter + self.GOAL_BLACKLIST_TICKS
            self._goal_blacklist[goal_name] = expires
            log(f"  [GoalReasoner] Blacklisted '{goal_name}' for {self.GOAL_BLACKLIST_TICKS} ticks")

    def advance(self):
        """Advance to next step in current plan (called after action succeeds)."""
        if self._current_plan:
            # Reset fail counter on successful execution
            if self._current_goal_name:
                self._goal_fail_count.pop(self._current_goal_name, None)
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

    @property
    def quest_tracker(self) -> Optional["QuestTracker"]:
        return self._quest_tracker

    @quest_tracker.setter
    def quest_tracker(self, tracker: Optional["QuestTracker"]) -> None:
        self._quest_tracker = tracker


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
