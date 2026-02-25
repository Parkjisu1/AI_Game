"""
GOAP Planner — Goal-Oriented Action Planning Core
===================================================
Forward A* search planner: finds cheapest action sequence
from current WorldState to satisfy a GOAPGoal.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import heapq


@dataclass
class WorldState:
    """Flat key-value game world state for GOAP planning."""
    props: Dict[str, Any] = field(default_factory=dict)

    def satisfies(self, conditions: Dict[str, Any]) -> bool:
        """Check if all conditions are met. Values can be exact match or callable predicates."""
        for key, expected in conditions.items():
            actual = self.props.get(key)
            if callable(expected):
                if not expected(actual):
                    return False
            elif actual != expected:
                return False
        return True

    def apply(self, effects: Dict[str, Any]) -> "WorldState":
        """Return new WorldState with effects applied. Effect values can be callables (transform functions)."""
        new_props = dict(self.props)
        for key, value in effects.items():
            if callable(value):
                new_props[key] = value(new_props.get(key))
            else:
                new_props[key] = value
        return WorldState(props=new_props)

    @staticmethod
    def from_snapshot(snapshot) -> "WorldState":
        """Convert GameStateSnapshot to WorldState."""
        props = {
            "screen_type": snapshot.screen_type,
            "hp_pct": snapshot.hp_pct,
            "mp_pct": snapshot.mp_pct,
            "gold": snapshot.gold,
            "level": snapshot.level,
        }
        # Add all gauges
        for name, gauge in snapshot.gauges.items():
            props[f"gauge_{name}"] = gauge.percentage
        # Add all resources
        for name, res in snapshot.resources.items():
            if res.parsed_value is not None:
                props[f"res_{name}"] = res.parsed_value
        # Add all stats
        for name, stat in snapshot.stats.items():
            if stat.parsed_value is not None:
                props[f"stat_{name}"] = stat.parsed_value
        return WorldState(props=props)

    def __hash__(self):
        # For A* closed set: hash on sorted tuple of serializable items
        items = []
        for k, v in sorted(self.props.items()):
            if isinstance(v, (int, float, str, bool)):
                items.append((k, v))
        return hash(tuple(items))

    def __eq__(self, other):
        if not isinstance(other, WorldState):
            return False
        return self.props == other.props


@dataclass
class GOAPAction:
    """An action the agent can take in the world."""
    name: str
    cost: float = 1.0
    preconditions: Dict[str, Any] = field(default_factory=dict)  # key -> value or callable predicate
    effects: Dict[str, Any] = field(default_factory=dict)        # key -> value or callable transform
    required_screen: Optional[str] = None    # screen navigation target
    execute_fn: Optional[Callable] = None    # function to call when on required_screen
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_applicable(self, state: WorldState) -> bool:
        return state.satisfies(self.preconditions)

    def apply_to(self, state: WorldState) -> WorldState:
        return state.apply(self.effects)


@dataclass
class GOAPGoal:
    """A desired world state to achieve."""
    name: str
    conditions: Dict[str, Any] = field(default_factory=dict)  # satisfaction conditions
    priority: float = 0.0  # set by UtilityScorer

    def is_satisfied(self, state: WorldState) -> bool:
        return state.satisfies(self.conditions)


@dataclass
class GOAPPlan:
    """A sequence of actions to achieve a goal."""
    goal: GOAPGoal
    actions: List[GOAPAction] = field(default_factory=list)
    total_cost: float = 0.0
    current_step: int = 0

    @property
    def is_complete(self) -> bool:
        return self.current_step >= len(self.actions)

    @property
    def current_action(self) -> Optional[GOAPAction]:
        if self.current_step < len(self.actions):
            return self.actions[self.current_step]
        return None

    def advance(self):
        self.current_step += 1


class GOAPPlanner:
    """Forward A* search planner: find action sequence from current state to goal."""
    MAX_PLAN_DEPTH = 10

    def __init__(self, actions: Optional[List[GOAPAction]] = None):
        self._actions = actions or []

    def set_actions(self, actions: List[GOAPAction]):
        self._actions = actions

    def add_action(self, action: GOAPAction):
        self._actions.append(action)

    def plan(self, current_state: WorldState, goal: GOAPGoal) -> Optional[GOAPPlan]:
        """Find cheapest action sequence to satisfy goal conditions.

        Uses forward A* search (expand from current state toward goal).
        Returns None if no plan found within MAX_PLAN_DEPTH.
        """
        if goal.is_satisfied(current_state):
            return GOAPPlan(goal=goal, actions=[], total_cost=0.0)

        # A* search: (cost, counter, state, action_chain)
        counter = 0
        open_set = []
        heapq.heappush(open_set, (0.0, counter, current_state, []))
        visited = set()

        while open_set:
            cost, _, state, chain = heapq.heappop(open_set)

            state_hash = hash(state)
            if state_hash in visited:
                continue
            visited.add(state_hash)

            if len(chain) >= self.MAX_PLAN_DEPTH:
                continue

            for action in self._actions:
                if not action.is_applicable(state):
                    continue
                new_state = action.apply_to(state)
                new_chain = chain + [action]
                new_cost = cost + action.cost

                if goal.is_satisfied(new_state):
                    return GOAPPlan(
                        goal=goal,
                        actions=new_chain,
                        total_cost=new_cost,
                    )

                counter += 1
                heapq.heappush(open_set, (new_cost, counter, new_state, new_chain))

        return None  # No plan found
