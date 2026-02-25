"""
Goal Library — Pre-defined Goals per Genre
============================================
Factory functions returning (GOAPActions, GoalScorers, GOAPGoals, InterruptRules)
for each supported genre. Serves as a registry of known goals and actions.
"""

from typing import Dict, List

from .goap_planner import GOAPAction, GOAPGoal
from .utility_scorer import Consideration, CurveType, GoalScorer


# ============================================================
# RPG Genre
# ============================================================

def get_rpg_actions() -> List[GOAPAction]:
    """RPG genre: standard action set."""
    return [
        GOAPAction(
            name="buy_potion",
            cost=2.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 100,
                "has_potion": False,
            },
            effects={
                "has_potion": True,
                "gold": lambda g: (g or 0) - 100,
            },
            required_screen="menu_shop",
            metadata={"category": "survival"},
        ),
        GOAPAction(
            name="use_potion",
            cost=1.0,
            preconditions={"has_potion": True},
            effects={
                "hp_pct": 1.0,
                "has_potion": False,
            },
            required_screen="battle",
            metadata={"category": "survival"},
        ),
        GOAPAction(
            name="equip_upgrade",
            cost=3.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 500,
                "has_upgrade_item": True,
            },
            effects={
                "gold": lambda g: (g or 0) - 500,
                "stat_atk": lambda v: (v or 0) + 10,
                "has_upgrade_item": False,
            },
            required_screen="menu_equipment",
            metadata={"category": "progression"},
        ),
        GOAPAction(
            name="do_quest",
            cost=4.0,
            preconditions={
                "has_active_quest": True,
                "hp_pct": lambda h: h is not None and h >= 0.3,
            },
            effects={
                "gold": lambda g: (g or 0) + 300,
                "gauge_xp": lambda x: min(1.0, (x or 0) + 0.2),
                "has_active_quest": False,
            },
            required_screen="quest_map",
            metadata={"category": "progression"},
        ),
        GOAPAction(
            name="grind_battle",
            cost=2.0,
            preconditions={
                "hp_pct": lambda h: h is not None and h >= 0.3,
            },
            effects={
                "gold": lambda g: (g or 0) + 100,
                "gauge_xp": lambda x: min(1.0, (x or 0) + 0.1),
            },
            required_screen="battle",
            metadata={"category": "grind"},
        ),
        GOAPAction(
            name="enhance_gear",
            cost=3.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 200,
            },
            effects={
                "gold": lambda g: (g or 0) - 200,
                "stat_def": lambda v: (v or 0) + 5,
            },
            required_screen="menu_equipment",
            metadata={"category": "progression"},
        ),
        GOAPAction(
            name="summon_hero",
            cost=5.0,
            preconditions={
                "res_gem": lambda g: g is not None and g >= 300,
            },
            effects={
                "res_gem": lambda g: (g or 0) - 300,
                "has_new_hero": True,
            },
            required_screen="menu_summon",
            metadata={"category": "gacha"},
        ),
    ]


def get_rpg_scorers() -> List[GoalScorer]:
    """RPG genre: utility scorers for each goal."""
    return [
        GoalScorer(
            goal_name="heal",
            considerations=[
                Consideration(
                    name="hp_inverse",
                    input_key="hp_pct",
                    curve_type=CurveType.INVERSE,
                    weight=2.0,
                ),
                Consideration(
                    name="has_potion",
                    input_key="has_potion",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="equip_upgrade",
            considerations=[
                Consideration(
                    name="gold_enough",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.01,
                    mid=500.0,
                    weight=1.0,
                ),
                Consideration(
                    name="hp_safe",
                    input_key="hp_pct",
                    curve_type=CurveType.SIGMOID,
                    k=10.0,
                    mid=0.6,
                    weight=0.8,
                ),
            ],
        ),
        GoalScorer(
            goal_name="do_quest",
            considerations=[
                Consideration(
                    name="has_quest",
                    input_key="has_active_quest",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=1.5,
                ),
                Consideration(
                    name="hp_sufficient",
                    input_key="hp_pct",
                    curve_type=CurveType.LINEAR,
                    m=1.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="grind",
            considerations=[
                Consideration(
                    name="xp_bar",
                    input_key="gauge_xp",
                    curve_type=CurveType.INVERSE,
                    weight=1.0,
                ),
                Consideration(
                    name="hp_safe_grind",
                    input_key="hp_pct",
                    curve_type=CurveType.STEP,
                    threshold=0.4,
                    weight=1.2,
                ),
            ],
        ),
        GoalScorer(
            goal_name="summon",
            considerations=[
                Consideration(
                    name="gem_enough",
                    input_key="res_gem",
                    curve_type=CurveType.SIGMOID,
                    k=0.02,
                    mid=300.0,
                    weight=1.0,
                ),
            ],
        ),
    ]


def get_rpg_goals() -> List[GOAPGoal]:
    """RPG genre: goal definitions."""
    return [
        GOAPGoal(
            name="heal",
            conditions={"hp_pct": lambda h: h is not None and h >= 0.9},
        ),
        GOAPGoal(
            name="equip_upgrade",
            conditions={"has_upgrade_item": False, "gold": lambda g: g is not None and g >= 500},
        ),
        GOAPGoal(
            name="do_quest",
            conditions={"has_active_quest": False},
        ),
        GOAPGoal(
            name="grind",
            conditions={"gauge_xp": lambda x: x is not None and x >= 0.8},
        ),
        GOAPGoal(
            name="summon",
            conditions={"has_new_hero": True},
        ),
    ]


def get_rpg_interrupts() -> List[dict]:
    """RPG genre: interrupt rules for emergency overrides."""
    return [
        {
            "name": "hp_critical",
            "condition": lambda world: (world.props.get("hp_pct") or 1.0) < 0.2,
            "goal_name": "heal",
            "priority": 100.0,
        },
        {
            "name": "mp_empty",
            "condition": lambda world: (world.props.get("mp_pct") or 1.0) < 0.1,
            "goal_name": "grind",  # fall back to basic grind when mp empty
            "priority": 80.0,
        },
    ]


# ============================================================
# Idle Genre (stub)
# ============================================================

def get_idle_actions() -> List[GOAPAction]:
    return [
        GOAPAction(
            name="collect_offline_rewards",
            cost=1.0,
            preconditions={"has_offline_rewards": True},
            effects={"has_offline_rewards": False, "gold": lambda g: (g or 0) + 1000},
            required_screen="main_lobby",
        ),
        GOAPAction(
            name="upgrade_building",
            cost=2.0,
            preconditions={"gold": lambda g: g is not None and g >= 500},
            effects={"gold": lambda g: (g or 0) - 500, "stat_atk": lambda v: (v or 0) + 1},
            required_screen="main_lobby",
        ),
        GOAPAction(
            name="start_expedition",
            cost=3.0,
            preconditions={"has_active_expedition": False},
            effects={"has_active_expedition": True},
            required_screen="expedition_map",
        ),
    ]


def get_idle_scorers() -> List[GoalScorer]:
    return [
        GoalScorer(
            goal_name="collect_rewards",
            considerations=[
                Consideration(
                    name="has_rewards",
                    input_key="has_offline_rewards",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=2.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="upgrade",
            considerations=[
                Consideration(
                    name="gold_plenty",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.002,
                    mid=1000.0,
                    weight=1.0,
                ),
            ],
        ),
    ]


def get_idle_goals() -> List[GOAPGoal]:
    return [
        GOAPGoal(
            name="collect_rewards",
            conditions={"has_offline_rewards": False},
        ),
        GOAPGoal(
            name="upgrade",
            conditions={"gold": lambda g: g is not None and g >= 1000},
        ),
    ]


def get_idle_interrupts() -> List[dict]:
    return [
        {
            "name": "offline_rewards_ready",
            "condition": lambda world: world.props.get("has_offline_rewards") is True,
            "goal_name": "collect_rewards",
            "priority": 90.0,
        },
    ]


# ============================================================
# Merge Genre (stub)
# ============================================================

def get_merge_actions() -> List[GOAPAction]:
    return [
        GOAPAction(
            name="merge_items",
            cost=1.0,
            preconditions={"has_mergeable_pair": True},
            effects={"has_mergeable_pair": False, "stat_atk": lambda v: (v or 0) + 5},
            required_screen="merge_board",
        ),
        GOAPAction(
            name="buy_merge_item",
            cost=2.0,
            preconditions={"gold": lambda g: g is not None and g >= 50},
            effects={"gold": lambda g: (g or 0) - 50, "has_mergeable_pair": True},
            required_screen="merge_shop",
        ),
    ]


def get_merge_scorers() -> List[GoalScorer]:
    return [
        GoalScorer(
            goal_name="merge",
            considerations=[
                Consideration(
                    name="has_pair",
                    input_key="has_mergeable_pair",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=2.0,
                ),
            ],
        ),
    ]


def get_merge_goals() -> List[GOAPGoal]:
    return [
        GOAPGoal(
            name="merge",
            conditions={"has_mergeable_pair": False},
        ),
    ]


def get_merge_interrupts() -> List[dict]:
    return []


# ============================================================
# SLG Genre (stub)
# ============================================================

def get_slg_actions() -> List[GOAPAction]:
    return [
        GOAPAction(
            name="train_troops",
            cost=3.0,
            preconditions={"gold": lambda g: g is not None and g >= 300},
            effects={"gold": lambda g: (g or 0) - 300, "troop_count": lambda t: (t or 0) + 100},
            required_screen="barracks",
        ),
        GOAPAction(
            name="attack_enemy",
            cost=4.0,
            preconditions={"troop_count": lambda t: t is not None and t >= 50},
            effects={"gold": lambda g: (g or 0) + 500, "troop_count": lambda t: max(0, (t or 0) - 20)},
            required_screen="world_map",
        ),
        GOAPAction(
            name="upgrade_castle",
            cost=5.0,
            preconditions={"gold": lambda g: g is not None and g >= 1000},
            effects={"gold": lambda g: (g or 0) - 1000, "castle_level": lambda l: (l or 0) + 1},
            required_screen="castle",
        ),
    ]


def get_slg_scorers() -> List[GoalScorer]:
    return [
        GoalScorer(
            goal_name="expand_army",
            considerations=[
                Consideration(
                    name="gold_available",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.005,
                    mid=500.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="attack",
            considerations=[
                Consideration(
                    name="troop_strength",
                    input_key="troop_count",
                    curve_type=CurveType.SIGMOID,
                    k=0.05,
                    mid=100.0,
                    weight=1.5,
                ),
            ],
        ),
    ]


def get_slg_goals() -> List[GOAPGoal]:
    return [
        GOAPGoal(
            name="expand_army",
            conditions={"troop_count": lambda t: t is not None and t >= 200},
        ),
        GOAPGoal(
            name="attack",
            conditions={"gold": lambda g: g is not None and g >= 500},
        ),
    ]


def get_slg_interrupts() -> List[dict]:
    return [
        {
            "name": "low_troops",
            "condition": lambda world: (world.props.get("troop_count") or 999) < 20,
            "goal_name": "expand_army",
            "priority": 95.0,
        },
    ]


# ============================================================
# Registry
# ============================================================

def get_goals_for_genre(genre: str) -> Dict:
    """Return {"actions": [...], "scorers": [...], "goals": [...], "interrupts": [...]} for the given genre."""
    genre_lower = genre.lower()

    if genre_lower == "rpg":
        return {
            "actions": get_rpg_actions(),
            "scorers": get_rpg_scorers(),
            "goals": get_rpg_goals(),
            "interrupts": get_rpg_interrupts(),
        }
    elif genre_lower == "idle":
        return {
            "actions": get_idle_actions(),
            "scorers": get_idle_scorers(),
            "goals": get_idle_goals(),
            "interrupts": get_idle_interrupts(),
        }
    elif genre_lower == "merge":
        return {
            "actions": get_merge_actions(),
            "scorers": get_merge_scorers(),
            "goals": get_merge_goals(),
            "interrupts": get_merge_interrupts(),
        }
    elif genre_lower == "slg":
        return {
            "actions": get_slg_actions(),
            "scorers": get_slg_scorers(),
            "goals": get_slg_goals(),
            "interrupts": get_slg_interrupts(),
        }
    else:
        # Generic fallback: empty sets
        return {
            "actions": [],
            "scorers": [],
            "goals": [],
            "interrupts": [],
        }
