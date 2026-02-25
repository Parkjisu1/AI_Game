"""
RPGSchema — RPG Genre Configuration
=====================================
Concepts, ROIs, goals, actions, and interrupt rules for RPG games.
Covers: battle, character management, inventory, shop, skill, quest, summon.
"""

from typing import Dict, List

from ..adb import log
from ..perception.gauge_reader import GaugeProfile
from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction, GOAPGoal, WorldState
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class RPGSchema(GenreSchema):
    """Genre schema for RPG games."""

    @property
    def genre_key(self) -> str:
        return "rpg"

    @property
    def genre_name(self) -> str:
        return "RPG"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "hp": GenreConcept(
                name="hp", category="gauge",
                description="Current health points percentage",
                default_gauge_profile="hp_green",
                is_required=True,
            ),
            "mp": GenreConcept(
                name="mp", category="gauge",
                description="Current mana/magic points percentage",
                default_gauge_profile="mp_blue",
                is_required=False,
            ),
            "xp": GenreConcept(
                name="xp", category="gauge",
                description="Experience points towards next level",
                default_gauge_profile="xp_yellow",
                is_required=False,
            ),
            "gold": GenreConcept(
                name="gold", category="resource",
                description="Primary soft currency",
                is_required=True,
            ),
            "gem": GenreConcept(
                name="gem", category="resource",
                description="Premium hard currency",
                is_required=False,
            ),
            "level": GenreConcept(
                name="level", category="stat",
                description="Character level",
                is_required=True,
            ),
            "atk": GenreConcept(
                name="atk", category="stat",
                description="Attack power",
                is_required=False,
            ),
            "def": GenreConcept(
                name="def", category="stat",
                description="Defense power",
                is_required=False,
            ),
            "potion_count": GenreConcept(
                name="potion_count", category="resource",
                description="Number of healing potions in inventory",
                is_required=False,
            ),
            "equipment_level": GenreConcept(
                name="equipment_level", category="stat",
                description="Average equipped item level",
                is_required=False,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "lobby": "Main hub screen",
            "battle": "Active battle / dungeon screen",
            "menu_character": "Character stats and skills",
            "menu_inventory": "Inventory and equipment management",
            "menu_shop": "In-game shop",
            "menu_skill": "Skill tree or upgrade screen",
            "stage_select": "Stage / dungeon selection",
            "summon": "Hero or equipment summon screen",
            "quest_list": "Quest board / mission list",
            "equipment_detail": "Single equipment detail view",
            "equipment_enhance": "Equipment enhancement / upgrade screen",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "battle": ScreenROI(
                screen_type="battle",
                gauge_regions={
                    "hp_bar": {
                        "region": [30, 60, 300, 20],
                        "profile": "hp_green",
                    },
                    "mp_bar": {
                        "region": [30, 90, 300, 14],
                        "profile": "mp_blue",
                    },
                },
                ocr_regions={
                    "stage_number": {
                        "region": [400, 20, 200, 30],
                        "numeric": False,
                        "name": "stage_number",
                    },
                },
            ),
            "lobby": ScreenROI(
                screen_type="lobby",
                gauge_regions={},
                ocr_regions={
                    "gold": {
                        "region": [20, 30, 200, 28],
                        "numeric": True,
                        "name": "gold",
                    },
                    "level": {
                        "region": [20, 70, 80, 24],
                        "numeric": True,
                        "name": "level",
                    },
                    "gem": {
                        "region": [250, 30, 150, 28],
                        "numeric": True,
                        "name": "gem",
                    },
                },
            ),
        }

    # ------------------------------------------------------------------
    # Gauge profiles
    # ------------------------------------------------------------------

    def get_gauge_profiles(self) -> List[GaugeProfile]:
        return [
            GaugeProfile(
                name="hp_green",
                hsv_lower=(35, 80, 80),
                hsv_upper=(85, 255, 255),
                color_rgb=(0, 200, 0),
            ),
            GaugeProfile(
                name="hp_red",
                hsv_lower=(0, 80, 80),
                hsv_upper=(10, 255, 255),
                color_rgb=(200, 0, 0),
                hsv_lower2=(170, 80, 80),
                hsv_upper2=(180, 255, 255),
            ),
            GaugeProfile(
                name="mp_blue",
                hsv_lower=(100, 80, 80),
                hsv_upper=(130, 255, 255),
                color_rgb=(0, 0, 200),
            ),
            GaugeProfile(
                name="xp_yellow",
                hsv_lower=(20, 80, 80),
                hsv_upper=(35, 255, 255),
                color_rgb=(200, 200, 0),
            ),
        ]

    # ------------------------------------------------------------------
    # Goal scorers
    # ------------------------------------------------------------------

    def get_goal_templates(self) -> List[GoalScorer]:
        return [
            GoalScorer(
                goal_name="heal",
                considerations=[
                    Consideration(
                        name="low_hp",
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
                goal_name="buy_supplies",
                considerations=[
                    Consideration(
                        name="has_gold",
                        input_key="gold_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.3,
                        weight=1.0,
                    ),
                    Consideration(
                        name="no_potion",
                        input_key="has_potion",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        invert=True,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="equip_upgrade",
                considerations=[
                    Consideration(
                        name="enough_gold",
                        input_key="gold_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.5,
                        weight=1.0,
                    ),
                    Consideration(
                        name="healthy",
                        input_key="hp_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="do_quest",
                considerations=[
                    Consideration(
                        name="healthy",
                        input_key="hp_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.4,
                        weight=1.0,
                    ),
                    Consideration(
                        name="has_quest",
                        input_key="has_active_quest",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="grind_battle",
                considerations=[
                    Consideration(
                        name="healthy",
                        input_key="hp_pct",
                        curve_type=CurveType.LINEAR,
                        m=1.0, b=0.0,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="enhance_gear",
                considerations=[
                    Consideration(
                        name="enough_gold",
                        input_key="gold_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.6,
                        weight=1.0,
                    ),
                    Consideration(
                        name="healthy",
                        input_key="hp_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="summon_hero",
                considerations=[
                    Consideration(
                        name="has_summon_currency",
                        input_key="gem_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.5,
                        weight=1.0,
                    ),
                ],
            ),
        ]

    # ------------------------------------------------------------------
    # GOAP actions
    # ------------------------------------------------------------------

    def get_action_templates(self) -> List[GOAPAction]:
        return [
            GOAPAction(
                name="go_shop",
                cost=1.5,
                preconditions={"screen_type": "lobby"},
                effects={"screen_type": "menu_shop"},
            ),
            GOAPAction(
                name="buy_potion",
                cost=2.0,
                preconditions={
                    "gold": lambda g: g is not None and g >= 100,
                    "has_potion": False,
                    "screen_type": "menu_shop",
                },
                effects={
                    "has_potion": True,
                    "gold": lambda g: (g or 0) - 100,
                },
                required_screen="menu_shop",
            ),
            GOAPAction(
                name="use_potion",
                cost=1.0,
                preconditions={"has_potion": True},
                effects={
                    "hp_pct": 1.0,
                    "has_potion": False,
                },
            ),
            GOAPAction(
                name="go_quest",
                cost=1.5,
                preconditions={"screen_type": "lobby"},
                effects={"screen_type": "quest_list"},
            ),
            GOAPAction(
                name="start_quest",
                cost=1.0,
                preconditions={
                    "screen_type": "quest_list",
                    "has_active_quest": False,
                },
                effects={"has_active_quest": True},
                required_screen="quest_list",
            ),
            GOAPAction(
                name="go_battle",
                cost=1.5,
                preconditions={
                    "screen_type": "lobby",
                    "hp_pct": lambda h: h is not None and h >= 0.3,
                },
                effects={"screen_type": "battle"},
            ),
            GOAPAction(
                name="grind",
                cost=3.0,
                preconditions={
                    "screen_type": "battle",
                    "hp_pct": lambda h: h is not None and h >= 0.3,
                },
                effects={
                    "gold": lambda g: (g or 0) + 50,
                    "xp_pct": lambda x: min(1.0, (x or 0) + 0.1),
                },
                required_screen="battle",
            ),
            GOAPAction(
                name="enhance_equipment",
                cost=3.0,
                preconditions={
                    "gold": lambda g: g is not None and g >= 500,
                    "has_upgrade_item": True,
                    "screen_type": "equipment_enhance",
                },
                effects={
                    "gold": lambda g: (g or 0) - 500,
                    "equipment_level": lambda v: (v or 0) + 1,
                    "has_upgrade_item": False,
                },
                required_screen="equipment_enhance",
            ),
        ]

    # ------------------------------------------------------------------
    # Interrupt rules
    # ------------------------------------------------------------------

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "hp_critical",
                "condition": lambda ws: (ws.props.get("hp_pct") or 1.0) < 0.2,
                "goal_name": "heal",
                "priority": 10.0,
            },
            {
                "name": "mp_empty",
                "condition": lambda ws: (ws.props.get("mp_pct") or 1.0) < 0.1,
                "goal_name": "restore_mp",
                "priority": 5.0,
            },
        ]
