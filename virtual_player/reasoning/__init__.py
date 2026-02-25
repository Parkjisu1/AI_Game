"""
Reasoning Package — Layer 2: Goal Reasoning
============================================
Provides GOAP planning, utility scoring, goal library, and
the main GoalReasoner orchestrator for autonomous agent decision-making.
"""

from .goap_planner import (
    WorldState,
    GOAPAction,
    GOAPGoal,
    GOAPPlan,
    GOAPPlanner,
)
from .utility_scorer import (
    CurveType,
    Consideration,
    GoalScorer,
    UtilityScorer,
)
from .goal_library import (
    get_rpg_actions,
    get_rpg_scorers,
    get_rpg_goals,
    get_rpg_interrupts,
    get_idle_actions,
    get_idle_scorers,
    get_idle_goals,
    get_idle_interrupts,
    get_merge_actions,
    get_merge_scorers,
    get_merge_goals,
    get_merge_interrupts,
    get_slg_actions,
    get_slg_scorers,
    get_slg_goals,
    get_slg_interrupts,
    get_goals_for_genre,
)
from .goal_reasoner import (
    InterruptRule,
    GoalReasoner,
    build_reasoner_for_genre,
)

__all__ = [
    # GOAP core
    "WorldState",
    "GOAPAction",
    "GOAPGoal",
    "GOAPPlan",
    "GOAPPlanner",
    # Utility scoring
    "CurveType",
    "Consideration",
    "GoalScorer",
    "UtilityScorer",
    # Goal library
    "get_rpg_actions",
    "get_rpg_scorers",
    "get_rpg_goals",
    "get_rpg_interrupts",
    "get_idle_actions",
    "get_idle_scorers",
    "get_idle_goals",
    "get_idle_interrupts",
    "get_merge_actions",
    "get_merge_scorers",
    "get_merge_goals",
    "get_merge_interrupts",
    "get_slg_actions",
    "get_slg_scorers",
    "get_slg_goals",
    "get_slg_interrupts",
    "get_goals_for_genre",
    # Orchestrator
    "InterruptRule",
    "GoalReasoner",
    "build_reasoner_for_genre",
]
