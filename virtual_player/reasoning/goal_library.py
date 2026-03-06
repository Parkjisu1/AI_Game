"""
Goal Library -- Pre-defined Goals per Genre
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
# RPG -- Ash & Veil variant (no HP bar, proxy-based)
# ============================================================

def _anv_move_button_check(screenshot_path, tap_fn) -> bool:
    """Check if 이동하기 button is active (blue). If grayed, detect and tap a different stage.

    Uses yellow pin detection to find stage icons dynamically, then taps
    the one furthest from the current (green) pin.

    Returns True if button is already active, False if it was grayed and we tried
    to activate it by tapping a different stage position.
    """
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(screenshot_path))
        if img is None:
            return True  # can't check, proceed anyway
        # Button pixel check at y=995, x=540 (from smart_player.py, adapted for cv2 BGR)
        btn_b = int(img[995, 540, 0])  # cv2 BGR: index 0=blue
        btn_r = int(img[995, 540, 2])  # cv2 BGR: index 2=red
        if btn_b > 100 and btn_r < 50:
            print("[PlayEngine] Move button is ACTIVE (blue)")
            return True

        # Button is grayed -- find stage pins via color detection
        print(f"[PlayEngine] Move button GRAYED (b={btn_b},r={btn_r}), finding stages...")
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Find green pin (current stage) -- only in map area (y: 200-900)
        map_hsv = hsv[200:900, :, :]
        green_mask = cv2.inRange(map_hsv, np.array([35, 100, 100]), np.array([85, 255, 255]))
        green_contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        green_cx, green_cy = 540, 500  # default center
        for c in sorted(green_contours, key=cv2.contourArea, reverse=True)[:1]:
            M = cv2.moments(c)
            if M["m00"] > 0:
                green_cx = int(M["m10"] / M["m00"])
                green_cy = int(M["m01"] / M["m00"]) + 200  # offset back to full image

        # Find stage markers -- yellow (completed) AND white/gray (available)
        # Yellow: H=15-35, S>100, V>150
        yellow_mask = cv2.inRange(map_hsv, np.array([15, 100, 150]), np.array([35, 255, 255]))
        # White/light gray: any hue, low saturation, high value
        white_mask = cv2.inRange(map_hsv, np.array([0, 0, 170]), np.array([180, 60, 255]))
        combined_mask = cv2.bitwise_or(yellow_mask, white_mask)
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for c in contours:
            area = cv2.contourArea(c)
            if 800 < area < 10000:  # filter noise and large decorations
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"]) + 200  # offset back
                    # Exclude if too close to green pin (same stage)
                    dist = ((cx - green_cx) ** 2 + (cy - green_cy) ** 2) ** 0.5
                    if dist > 80:
                        candidates.append((cx, cy, dist))

        if candidates:
            # Sort by distance from green pin (furthest first = most different stage)
            candidates.sort(key=lambda p: p[2], reverse=True)
            tx, ty, d = candidates[0]
            print(f"[PlayEngine] Tapping stage at ({tx},{ty}), dist={d:.0f} from green")
            tap_fn(tx, ty, 1.5)
            return False

        # Fallback: hardcoded positions for common map layouts
        import random
        _FALLBACK = [(284, 414), (519, 603), (815, 732), (300, 835)]
        pos = random.choice(_FALLBACK)
        print(f"[PlayEngine] No pins found, fallback tap at {pos}")
        tap_fn(pos[0], pos[1], 1.5)
        return False
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("move button check error: %s", e)
        return True  # proceed on error


def get_rpg_anv_actions() -> List[GOAPAction]:
    """RPG Ash & Veil: actions using observable proxy keys (no hp_pct)."""
    return [
        GOAPAction(
            name="buy_potion",
            cost=2.0,  # higher priority than grind when MP is low
            preconditions={
                "needs_potion": True,
            },
            effects={
                "needs_potion": False,
                "gold": lambda g: (g or 0) - 200,
                "mp_pct": 1.0,
            },
            required_screen="lobby",
            blocked_screens=["battle", "loading"],  # can't leave mid-combat
            metadata={
                "category": "survival",
                "tap_x": 100, "tap_y": 1700,  # Potion shop in town bottom bar
                "wait": 3.0,
            },
        ),
        GOAPAction(
            name="enhance_gear",
            cost=4.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 1000,
            },
            effects={
                "gold": lambda g: (g or 0) - 500,
                "stat_def": lambda v: (v or 0) + 5,
            },
            required_screen="menu_character",
            metadata={"category": "progression"},
        ),
        GOAPAction(
            name="grind_battle",
            cost=1.0,  # lowest cost -> default fallback for starting battle
            preconditions={
                "screen_type": lambda s: s in (None, "stage_select", "lobby", "loading"),
            },
            effects={
                "gold": lambda g: (g or 0) + 200,
                "gauge_xp": lambda x: min(1.0, (x or 0) + 0.05),
                "battles_since_shop": lambda b: (b or 0) + 1,
            },
            required_screen="stage_select",
            metadata={
                "category": "grind",
                "tap_x": 540, "tap_y": 1010,  # "이동하기" button (smart_player verified)
                "wait": 5.0,  # loading screen takes time
                "pre_tap_check": _anv_move_button_check,  # check if button is active
            },
        ),
        GOAPAction(
            name="wait_in_battle",
            cost=1.0,  # same cost as grind_battle
            preconditions={
                "screen_type": lambda s: s == "battle",
            },
            effects={
                "gold": lambda g: (g or 0) + 200,
                "gauge_xp": lambda x: min(1.0, (x or 0) + 0.05),
                "battles_since_shop": lambda b: (b or 0) + 1,
            },
            required_screen="battle",
            metadata={
                "category": "grind",
                "wait": 5.0,  # just wait for auto-battle to proceed
            },
        ),
        GOAPAction(
            name="equip_upgrade",
            cost=5.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 2000,
            },
            effects={
                "gold": lambda g: (g or 0) - 1000,
                "stat_atk": lambda v: (v or 0) + 10,
            },
            required_screen="menu_character",
            metadata={"category": "progression"},
        ),
    ]


def get_rpg_anv_scorers() -> List[GoalScorer]:
    """RPG Ash & Veil: utility scorers (no hp_pct considerations)."""
    return [
        GoalScorer(
            goal_name="buy_supplies",
            considerations=[
                Consideration(
                    name="needs_potion",
                    input_key="needs_potion",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=2.0,
                ),
                Consideration(
                    name="gold_enough_potion",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.005,
                    mid=500.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="enhance",
            considerations=[
                Consideration(
                    name="gold_plenty",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.002,
                    mid=5000.0,
                    weight=1.5,
                ),
            ],
        ),
        GoalScorer(
            goal_name="equip",
            considerations=[
                Consideration(
                    name="gold_rich",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.001,
                    mid=10000.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="grind",
            considerations=[
                Consideration(
                    name="xp_bar_low",
                    input_key="gauge_xp",
                    curve_type=CurveType.INVERSE,
                    weight=0.8,
                ),
            ],
        ),
    ]


def get_rpg_anv_goals() -> List[GOAPGoal]:
    """RPG Ash & Veil: goal definitions."""
    return [
        GOAPGoal(
            name="buy_supplies",
            conditions={"needs_potion": False},
        ),
        GOAPGoal(
            name="enhance",
            conditions={"stat_def": lambda d: d is not None and d >= 50},
        ),
        GOAPGoal(
            name="equip",
            conditions={"stat_atk": lambda a: a is not None and a >= 100},
        ),
        GOAPGoal(
            name="grind",
            conditions={"battles_since_shop": lambda b: b is not None and b >= 1},
        ),
    ]


def get_rpg_anv_interrupts() -> List[dict]:
    """RPG Ash & Veil: interrupt rules (proxy-based, no HP)."""
    return [
        {
            "name": "death_recovery",
            "condition": lambda world: world.props.get("needs_potion") is True,
            "goal_name": "buy_supplies",
            "priority": 90.0,
        },
        {
            "name": "gold_cap",
            "condition": lambda world: (world.props.get("gold") or 0) > 50000,
            "goal_name": "enhance",
            "priority": 70.0,
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
# Puzzle Genre
# ============================================================

def get_puzzle_actions() -> List[GOAPAction]:
    """Puzzle genre: standard action set."""
    return [
        GOAPAction(
            name="play_level",
            cost=1.0,
            preconditions={},
            effects={
                "score": lambda s: (s or 0) + 100,
                "level": lambda l: (l or 0) + 1,
            },
            required_screen="gameplay",
        ),
        GOAPAction(
            name="use_booster",
            cost=2.0,
            preconditions={
                "boosters": lambda b: b is not None and b >= 1,
            },
            effects={
                "boosters": lambda b: (b or 0) - 1,
                "score": lambda s: (s or 0) + 200,
            },
        ),
        GOAPAction(
            name="retry_level",
            cost=1.5,
            preconditions={
                "lives": lambda l: l is not None and l >= 1,
            },
            effects={
                "lives": lambda l: (l or 0) - 1,
            },
        ),
    ]


def get_puzzle_scorers() -> List[GoalScorer]:
    """Puzzle genre: utility scorers for each goal."""
    return [
        GoalScorer(
            goal_name="play",
            considerations=[
                Consideration(
                    name="lives_available",
                    input_key="lives",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=2.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="use_booster",
            considerations=[
                Consideration(
                    name="booster_count",
                    input_key="boosters",
                    curve_type=CurveType.SIGMOID,
                    k=1.0,
                    mid=1.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="retry",
            considerations=[
                Consideration(
                    name="lives_remaining",
                    input_key="lives",
                    curve_type=CurveType.LINEAR,
                    m=1.0,
                    weight=0.5,
                ),
            ],
        ),
    ]


def get_puzzle_goals() -> List[GOAPGoal]:
    """Puzzle genre: goal definitions."""
    return [
        GOAPGoal(
            name="play",
            conditions={"level": lambda l: l is not None and l >= 1},
        ),
        GOAPGoal(
            name="use_booster",
            conditions={"score": lambda s: s is not None and s >= 500},
        ),
        GOAPGoal(
            name="retry",
            conditions={"lives": lambda l: l is not None and l > 0},
        ),
    ]


def get_puzzle_interrupts() -> List[dict]:
    """Puzzle genre: interrupt rules for emergency overrides."""
    return [
        {
            "name": "lives_depleted",
            "condition": lambda world: (world.props.get("lives") or 1) <= 0,
            "goal_name": "wait_for_lives",
            "priority": 100.0,
        },
        {
            "name": "stuck_detector",
            "condition": lambda world: (world.props.get("same_score_ticks") or 0) >= 3,
            "goal_name": "use_booster",
            "priority": 80.0,
        },
    ]


# ============================================================
# Tycoon Genre
# ============================================================

def get_tycoon_actions() -> List[GOAPAction]:
    """Tycoon genre: standard action set."""
    return [
        GOAPAction(
            name="upgrade_building",
            cost=3.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 500,
            },
            effects={
                "gold": lambda g: (g or 0) - 500,
                "buildings": lambda b: (b or 0) + 1,
            },
        ),
        GOAPAction(
            name="hire_staff",
            cost=2.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 200,
            },
            effects={
                "gold": lambda g: (g or 0) - 200,
                "staff": lambda s: (s or 0) + 1,
            },
        ),
        GOAPAction(
            name="collect_revenue",
            cost=1.0,
            preconditions={
                "has_revenue": True,
            },
            effects={
                "has_revenue": False,
                "gold": lambda g: (g or 0) + 500,
            },
        ),
        GOAPAction(
            name="research",
            cost=4.0,
            preconditions={
                "gold": lambda g: g is not None and g >= 1000,
            },
            effects={
                "gold": lambda g: (g or 0) - 1000,
                "research_level": lambda r: (r or 0) + 1,
            },
        ),
    ]


def get_tycoon_scorers() -> List[GoalScorer]:
    """Tycoon genre: utility scorers for each goal."""
    return [
        GoalScorer(
            goal_name="expand",
            considerations=[
                Consideration(
                    name="gold_for_building",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.002,
                    mid=1000.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="hire",
            considerations=[
                Consideration(
                    name="gold_for_staff",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.005,
                    mid=500.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="collect",
            considerations=[
                Consideration(
                    name="revenue_ready",
                    input_key="has_revenue",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="research",
            considerations=[
                Consideration(
                    name="gold_for_research",
                    input_key="gold",
                    curve_type=CurveType.SIGMOID,
                    k=0.001,
                    mid=2000.0,
                    weight=1.0,
                ),
            ],
        ),
    ]


def get_tycoon_goals() -> List[GOAPGoal]:
    """Tycoon genre: goal definitions."""
    return [
        GOAPGoal(
            name="expand",
            conditions={"buildings": lambda b: b is not None and b >= 1},
        ),
        GOAPGoal(
            name="hire",
            conditions={"staff": lambda s: s is not None and s >= 1},
        ),
        GOAPGoal(
            name="collect",
            conditions={"has_revenue": False},
        ),
        GOAPGoal(
            name="research",
            conditions={"research_level": lambda r: r is not None and r >= 1},
        ),
    ]


def get_tycoon_interrupts() -> List[dict]:
    """Tycoon genre: interrupt rules for emergency overrides."""
    return [
        {
            "name": "revenue_full",
            "condition": lambda world: world.props.get("has_revenue") is True,
            "goal_name": "collect",
            "priority": 90.0,
        },
        {
            "name": "satisfaction_low",
            "condition": lambda world: (world.props.get("satisfaction") or 1.0) < 0.3,
            "goal_name": "hire",
            "priority": 85.0,
        },
    ]


# ============================================================
# Simulation Genre
# ============================================================

def get_simulation_actions() -> List[GOAPAction]:
    """Simulation genre: standard action set."""
    return [
        GOAPAction(
            name="build_structure",
            cost=3.0,
            preconditions={
                "resources": lambda r: r is not None and r >= 500,
            },
            effects={
                "resources": lambda r: (r or 0) - 500,
                "buildings": lambda b: (b or 0) + 1,
            },
        ),
        GOAPAction(
            name="adjust_taxes",
            cost=1.0,
            preconditions={},
            effects={
                "happiness": lambda h: max(0.0, (h or 0) - 0.05),
                "budget": lambda b: (b or 0) + 200,
            },
        ),
        GOAPAction(
            name="respond_event",
            cost=2.0,
            preconditions={
                "has_event": True,
            },
            effects={
                "has_event": False,
                "happiness": lambda h: min(1.0, (h or 0) + 0.1),
            },
        ),
        GOAPAction(
            name="upgrade_service",
            cost=4.0,
            preconditions={
                "resources": lambda r: r is not None and r >= 1000,
            },
            effects={
                "resources": lambda r: (r or 0) - 1000,
                "happiness": lambda h: min(1.0, (h or 0) + 0.2),
                "service_level": lambda s: (s or 0) + 1,
            },
        ),
    ]


def get_simulation_scorers() -> List[GoalScorer]:
    """Simulation genre: utility scorers for each goal."""
    return [
        GoalScorer(
            goal_name="build",
            considerations=[
                Consideration(
                    name="resources_for_build",
                    input_key="resources",
                    curve_type=CurveType.SIGMOID,
                    k=0.002,
                    mid=800.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="manage",
            considerations=[
                Consideration(
                    name="happiness_low",
                    input_key="happiness",
                    curve_type=CurveType.INVERSE,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="event",
            considerations=[
                Consideration(
                    name="event_pending",
                    input_key="has_event",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="upgrade",
            considerations=[
                Consideration(
                    name="resources_for_upgrade",
                    input_key="resources",
                    curve_type=CurveType.SIGMOID,
                    k=0.001,
                    mid=1500.0,
                    weight=1.0,
                ),
            ],
        ),
    ]


def get_simulation_goals() -> List[GOAPGoal]:
    """Simulation genre: goal definitions."""
    return [
        GOAPGoal(
            name="build",
            conditions={"buildings": lambda b: b is not None and b >= 1},
        ),
        GOAPGoal(
            name="manage",
            conditions={"happiness": lambda h: h is not None and h >= 0.7},
        ),
        GOAPGoal(
            name="event",
            conditions={"has_event": False},
        ),
        GOAPGoal(
            name="upgrade",
            conditions={"service_level": lambda s: s is not None and s >= 1},
        ),
    ]


def get_simulation_interrupts() -> List[dict]:
    """Simulation genre: interrupt rules for emergency overrides."""
    return [
        {
            "name": "happiness_critical",
            "condition": lambda world: (world.props.get("happiness") or 1.0) < 0.2,
            "goal_name": "manage",
            "priority": 95.0,
        },
        {
            "name": "budget_negative",
            "condition": lambda world: (world.props.get("budget") or 0) < 0,
            "goal_name": "manage",
            "priority": 90.0,
        },
    ]


# ============================================================
# Casual Genre
# ============================================================

def get_casual_actions() -> List[GOAPAction]:
    """Casual genre: standard action set."""
    return [
        GOAPAction(
            name="play_level",
            cost=1.0,
            preconditions={
                "lives": lambda l: l is not None and l >= 1,
            },
            effects={
                "lives": lambda l: (l or 0) - 1,
                "level": lambda l: (l or 0) + 1,
            },
        ),
        GOAPAction(
            name="use_booster",
            cost=2.0,
            preconditions={
                "boosters": lambda b: b is not None and b >= 1,
            },
            effects={
                "boosters": lambda b: (b or 0) - 1,
                "score": lambda s: (s or 0) + 200,
            },
        ),
        GOAPAction(
            name="buy_lives",
            cost=3.0,
            preconditions={
                "coins": lambda c: c is not None and c >= 100,
            },
            effects={
                "coins": lambda c: (c or 0) - 100,
                "lives": lambda l: (l or 0) + 5,
            },
        ),
        GOAPAction(
            name="claim_daily",
            cost=1.0,
            preconditions={
                "has_daily": True,
            },
            effects={
                "has_daily": False,
                "coins": lambda c: (c or 0) + 50,
            },
        ),
    ]


def get_casual_scorers() -> List[GoalScorer]:
    """Casual genre: utility scorers for each goal."""
    return [
        GoalScorer(
            goal_name="play",
            considerations=[
                Consideration(
                    name="lives_available",
                    input_key="lives",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="boost",
            considerations=[
                Consideration(
                    name="booster_count",
                    input_key="boosters",
                    curve_type=CurveType.SIGMOID,
                    k=1.0,
                    mid=1.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="buy",
            considerations=[
                Consideration(
                    name="coins_enough",
                    input_key="coins",
                    curve_type=CurveType.SIGMOID,
                    k=0.01,
                    mid=200.0,
                    weight=1.0,
                ),
            ],
        ),
        GoalScorer(
            goal_name="daily",
            considerations=[
                Consideration(
                    name="daily_ready",
                    input_key="has_daily",
                    curve_type=CurveType.STEP,
                    threshold=0.5,
                    weight=1.0,
                ),
            ],
        ),
    ]


def get_casual_goals() -> List[GOAPGoal]:
    """Casual genre: goal definitions."""
    return [
        GOAPGoal(
            name="play",
            conditions={"level": lambda l: l is not None and l >= 1},
        ),
        GOAPGoal(
            name="boost",
            conditions={"score": lambda s: s is not None and s >= 500},
        ),
        GOAPGoal(
            name="buy",
            conditions={"lives": lambda l: l is not None and l >= 3},
        ),
        GOAPGoal(
            name="daily",
            conditions={"has_daily": False},
        ),
    ]


def get_casual_interrupts() -> List[dict]:
    """Casual genre: interrupt rules for emergency overrides."""
    return [
        {
            "name": "no_lives",
            "condition": lambda world: (world.props.get("lives") or 1) <= 0,
            "goal_name": "buy",
            "priority": 95.0,
        },
        {
            "name": "daily_available",
            "condition": lambda world: world.props.get("has_daily") is True,
            "goal_name": "claim_daily",
            "priority": 80.0,
        },
    ]


# ============================================================
# Quest Helpers (cross-genre)
# ============================================================

def get_quest_actions() -> List[GOAPAction]:
    """Generic quest-related actions usable across all genres.

    These are baseline fallbacks. QuestTracker.decompose_to_actions() generates
    objective-specific actions dynamically and injects them via GoalReasoner.
    """
    return [
        GOAPAction(
            name="navigate_to_quest_board",
            cost=1.5,
            preconditions={},
            effects={"screen_type": "quest_map"},
            metadata={"type": "navigate", "category": "quest"},
        ),
        GOAPAction(
            name="accept_quest",
            cost=1.0,
            preconditions={"screen_type": "quest_map"},
            effects={"has_active_quest": True},
            required_screen="quest_map",
            metadata={"type": "interact", "category": "quest"},
        ),
        GOAPAction(
            name="submit_quest",
            cost=1.0,
            preconditions={
                "screen_type": "quest_map",
                "has_active_quest": True,
            },
            effects={
                "has_active_quest": False,
                "gold": lambda g: (g or 0) + 300,
                "gauge_xp": lambda x: min(1.0, (x or 0) + 0.15),
            },
            required_screen="quest_map",
            metadata={"type": "interact", "category": "quest"},
        ),
    ]


def get_quest_scorer() -> GoalScorer:
    """Utility scorer for the cross-genre 'do_quest' goal.

    Scores highly when a quest is active and HP/health is sufficient.
    """
    return GoalScorer(
        goal_name="do_quest",
        considerations=[
            Consideration(
                name="has_quest",
                input_key="has_active_quest",
                curve_type=CurveType.STEP,
                threshold=0.5,
                weight=2.0,
            ),
            Consideration(
                name="quest_progress",
                input_key="quest_kill_progress",
                curve_type=CurveType.INVERSE,  # more urgent the less progress made
                weight=1.0,
            ),
        ],
    )


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
    elif genre_lower == "rpg_anv":
        return {
            "actions": get_rpg_anv_actions(),
            "scorers": get_rpg_anv_scorers(),
            "goals": get_rpg_anv_goals(),
            "interrupts": get_rpg_anv_interrupts(),
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
    elif genre_lower == "puzzle":
        return {
            "actions": get_puzzle_actions(),
            "scorers": get_puzzle_scorers(),
            "goals": get_puzzle_goals(),
            "interrupts": get_puzzle_interrupts(),
        }
    elif genre_lower == "tycoon":
        return {
            "actions": get_tycoon_actions(),
            "scorers": get_tycoon_scorers(),
            "goals": get_tycoon_goals(),
            "interrupts": get_tycoon_interrupts(),
        }
    elif genre_lower == "simulation":
        return {
            "actions": get_simulation_actions(),
            "scorers": get_simulation_scorers(),
            "goals": get_simulation_goals(),
            "interrupts": get_simulation_interrupts(),
        }
    elif genre_lower == "casual":
        return {
            "actions": get_casual_actions(),
            "scorers": get_casual_scorers(),
            "goals": get_casual_goals(),
            "interrupts": get_casual_interrupts(),
        }
    else:
        # Generic fallback: empty sets
        return {
            "actions": [],
            "scorers": [],
            "goals": [],
            "interrupts": [],
        }


# ============================================================
# Nav Graph Enrichment
# ============================================================

# Category keyword -> nav_graph element keyword mapping
_CATEGORY_ELEMENT_MAP = {
    "survival": ["potion", "recovery", "item_potion", "mana_recovery"],
    "progression": ["enhance", "equipment", "upgrade", "gear"],
    "grind": ["auto", "battle", "skill", "auto_button"],
    "gacha": ["summon", "card", "premium_card"],
}


def enrich_actions_from_nav_graph(
    actions: List[GOAPAction],
    nav_graph,
) -> int:
    """Populate tap_x/tap_y in GOAPAction metadata from nav_graph in_screen_actions.

    Uses keyword matching between action metadata["category"] and
    nav_graph element names to find relevant tap coordinates.

    Args:
        actions: List of GOAPAction instances to enrich.
        nav_graph: NavigationGraph with nodes containing in_screen_actions.

    Returns:
        Number of actions enriched.
    """
    enriched = 0

    for action in actions:
        # Skip if already has coordinates
        if action.metadata.get("tap_x") is not None:
            continue

        category = action.metadata.get("category", "")
        keywords = _CATEGORY_ELEMENT_MAP.get(category, [])
        if not keywords:
            continue

        # Search the action's required_screen node first
        target_screen = action.required_screen
        screens_to_search = []
        if target_screen and target_screen in nav_graph.nodes:
            screens_to_search.append(target_screen)
        # Also search all nodes as fallback
        for screen_type in nav_graph.nodes:
            if screen_type not in screens_to_search:
                screens_to_search.append(screen_type)

        for screen_type in screens_to_search:
            in_actions = nav_graph.get_in_screen_actions(screen_type)
            for in_act in in_actions:
                if in_act.get("category") == "idle":
                    continue
                element = in_act.get("element", "").lower()
                if any(kw in element for kw in keywords):
                    action.metadata["tap_x"] = in_act.get("x", 540)
                    action.metadata["tap_y"] = in_act.get("y", 960)
                    action.metadata["enriched_from"] = f"{screen_type}:{element}"
                    enriched += 1
                    break
            if action.metadata.get("tap_x") is not None:
                break

    return enriched
