"""
SLGSchema -- Strategy (SLG) Genre Configuration
================================================
Concepts, ROIs, goals, actions, and interrupt rules for SLG / 4X Strategy games.
Focus: resource gathering, troop training, territory expansion, base defense.
"""

from typing import Dict, List

from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class SLGSchema(GenreSchema):
    """Genre schema for SLG (Strategy / 4X) games."""

    @property
    def genre_key(self) -> str:
        return "slg"

    @property
    def genre_name(self) -> str:
        return "SLG"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "base_power": GenreConcept(
                name="base_power", category="stat",
                description="Overall base / kingdom power rating",
                is_required=True,
            ),
            "army_size": GenreConcept(
                name="army_size", category="resource",
                description="Total number of trained troops",
                is_required=True,
            ),
            "food": GenreConcept(
                name="food", category="resource",
                description="Food resource for troop upkeep",
                is_required=True,
            ),
            "wood": GenreConcept(
                name="wood", category="resource",
                description="Wood resource for construction",
                is_required=True,
            ),
            "stone": GenreConcept(
                name="stone", category="resource",
                description="Stone resource for buildings",
                is_required=True,
            ),
            "iron": GenreConcept(
                name="iron", category="resource",
                description="Iron resource for equipment and troops",
                is_required=False,
            ),
            "territory_count": GenreConcept(
                name="territory_count", category="stat",
                description="Number of tiles / territories controlled",
                is_required=False,
            ),
            "builder_slots": GenreConcept(
                name="builder_slots", category="resource",
                description="Available construction slots",
                is_required=False,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "base_view": "Player's base / kingdom overview",
            "world_map": "World map with territories and enemy tiles",
            "barracks": "Troop training facility",
            "resource_field": "Resource gathering field detail",
            "research": "Technology research tree",
            "rally": "Rally / march management screen",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "base_view": ScreenROI(
                screen_type="base_view",
                gauge_regions={},
                ocr_regions={
                    "food": {
                        "region": [10, 80, 120, 24],
                        "numeric": True,
                        "name": "food",
                    },
                    "wood": {
                        "region": [140, 80, 120, 24],
                        "numeric": True,
                        "name": "wood",
                    },
                    "stone": {
                        "region": [270, 80, 120, 24],
                        "numeric": True,
                        "name": "stone",
                    },
                    "iron": {
                        "region": [400, 80, 120, 24],
                        "numeric": True,
                        "name": "iron",
                    },
                    "base_power": {
                        "region": [10, 30, 200, 28],
                        "numeric": True,
                        "name": "base_power",
                    },
                },
            ),
            "barracks": ScreenROI(
                screen_type="barracks",
                gauge_regions={},
                ocr_regions={
                    "army_size": {
                        "region": [20, 100, 160, 28],
                        "numeric": True,
                        "name": "army_size",
                    },
                    "training_slots": {
                        "region": [200, 100, 100, 28],
                        "numeric": True,
                        "name": "training_slots",
                    },
                },
            ),
        }

    # ------------------------------------------------------------------
    # Goal scorers
    # ------------------------------------------------------------------

    def get_goal_templates(self) -> List[GoalScorer]:
        return [
            GoalScorer(
                goal_name="gather_resources",
                considerations=[
                    Consideration(
                        name="low_resources",
                        input_key="resource_pct",
                        curve_type=CurveType.INVERSE,
                        weight=1.5,
                    ),
                    Consideration(
                        name="gatherer_available",
                        input_key="march_slots_free",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="train_troops",
                considerations=[
                    Consideration(
                        name="low_army",
                        input_key="army_fill_pct",
                        curve_type=CurveType.INVERSE,
                        weight=1.5,
                    ),
                    Consideration(
                        name="has_food",
                        input_key="food_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.3,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="expand_territory",
                considerations=[
                    Consideration(
                        name="strong_army",
                        input_key="army_fill_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.6,
                        weight=1.5,
                    ),
                    Consideration(
                        name="march_available",
                        input_key="march_slots_free",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="defend_base",
                considerations=[
                    Consideration(
                        name="under_threat",
                        input_key="threat_level",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.5,
                        weight=2.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="upgrade_buildings",
                considerations=[
                    Consideration(
                        name="has_resources",
                        input_key="resource_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.5,
                        weight=1.0,
                    ),
                    Consideration(
                        name="builder_free",
                        input_key="builder_slots",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="research_tech",
                considerations=[
                    Consideration(
                        name="has_resources",
                        input_key="resource_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.4,
                        weight=1.0,
                    ),
                    Consideration(
                        name="research_available",
                        input_key="research_slot_free",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
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
                name="dispatch_gather",
                cost=2.0,
                preconditions={
                    "march_slots_free": lambda s: s is not None and s >= 1,
                    "screen_type": "world_map",
                },
                effects={
                    "march_slots_free": lambda s: max(0, (s or 0) - 1),
                    "gather_marches_active": lambda m: (m or 0) + 1,
                },
                required_screen="world_map",
            ),
            GOAPAction(
                name="train_unit",
                cost=3.0,
                preconditions={
                    "food": lambda f: f is not None and f >= 100,
                    "training_slots": lambda s: s is not None and s >= 1,
                    "screen_type": "barracks",
                },
                effects={
                    "food": lambda f: (f or 0) - 100,
                    "army_size": lambda a: (a or 0) + 50,
                },
                required_screen="barracks",
            ),
            GOAPAction(
                name="scout_tile",
                cost=2.0,
                preconditions={
                    "march_slots_free": lambda s: s is not None and s >= 1,
                    "screen_type": "world_map",
                },
                effects={
                    "scouted_tiles": lambda t: (t or 0) + 1,
                    "march_slots_free": lambda s: max(0, (s or 0) - 1),
                },
                required_screen="world_map",
            ),
            GOAPAction(
                name="attack_tile",
                cost=5.0,
                preconditions={
                    "army_size": lambda a: a is not None and a >= 500,
                    "march_slots_free": lambda s: s is not None and s >= 1,
                    "screen_type": "world_map",
                },
                effects={
                    "territory_count": lambda t: (t or 0) + 1,
                    "army_size": lambda a: max(0, (a or 0) - 50),
                    "march_slots_free": lambda s: max(0, (s or 0) - 1),
                },
                required_screen="world_map",
            ),
            GOAPAction(
                name="start_building",
                cost=3.0,
                preconditions={
                    "builder_slots": lambda b: b is not None and b >= 1,
                    "wood": lambda w: w is not None and w >= 200,
                    "stone": lambda s: s is not None and s >= 100,
                    "screen_type": "base_view",
                },
                effects={
                    "builder_slots": lambda b: max(0, (b or 0) - 1),
                    "wood": lambda w: (w or 0) - 200,
                    "stone": lambda s: (s or 0) - 100,
                },
                required_screen="base_view",
            ),
            GOAPAction(
                name="start_research",
                cost=3.0,
                preconditions={
                    "research_slot_free": True,
                    "food": lambda f: f is not None and f >= 50,
                    "screen_type": "research",
                },
                effects={
                    "research_slot_free": False,
                    "food": lambda f: (f or 0) - 50,
                },
                required_screen="research",
            ),
        ]

    # ------------------------------------------------------------------
    # Interrupt rules
    # ------------------------------------------------------------------

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "under_attack",
                "condition": lambda ws: (ws.props.get("threat_level") or 0.0) >= 0.7,
                "goal_name": "defend_base",
                "priority": 10.0,
            },
            {
                "name": "resource_depleted",
                "condition": lambda ws: (ws.props.get("resource_pct") or 1.0) < 0.1,
                "goal_name": "gather_resources",
                "priority": 8.0,
            },
            {
                "name": "builder_idle",
                "condition": lambda ws: (ws.props.get("builder_slots") or 0) >= 1,
                "goal_name": "upgrade_buildings",
                "priority": 4.0,
            },
        ]
