"""
IdleSchema -- Idle Genre Configuration
=======================================
Concepts, ROIs, goals, actions, and interrupt rules for Idle/Incremental games.
Focus: resource accumulation, offline rewards, upgrades, prestige.
"""

from typing import Dict, List

from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class IdleSchema(GenreSchema):
    """Genre schema for Idle / Incremental games."""

    @property
    def genre_key(self) -> str:
        return "idle"

    @property
    def genre_name(self) -> str:
        return "Idle"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "main_resource": GenreConcept(
                name="main_resource", category="resource",
                description="Primary accumulating resource (coins, gold, power)",
                is_required=True,
            ),
            "premium_currency": GenreConcept(
                name="premium_currency", category="resource",
                description="Hard currency used for boosts and special upgrades",
                is_required=False,
            ),
            "offline_reward": GenreConcept(
                name="offline_reward", category="special",
                description="Resources accumulated while offline",
                is_required=False,
            ),
            "prestige_points": GenreConcept(
                name="prestige_points", category="resource",
                description="Meta currency from prestige resets",
                is_required=False,
            ),
            "hero_level": GenreConcept(
                name="hero_level", category="stat",
                description="Main hero or unit upgrade level",
                is_required=True,
            ),
            "auto_speed": GenreConcept(
                name="auto_speed", category="stat",
                description="Automation speed multiplier",
                is_required=False,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "lobby": "Main idle screen with active progress",
            "idle_screen": "Core idle / clicker game area",
            "upgrade": "Hero or building upgrade panel",
            "prestige": "Prestige / ascension screen",
            "shop": "In-game shop for boosts",
            "offline_reward": "Offline reward claim popup",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "idle_screen": ScreenROI(
                screen_type="idle_screen",
                gauge_regions={},
                ocr_regions={
                    "main_resource": {
                        "region": [100, 20, 340, 30],
                        "numeric": True,
                        "name": "main_resource",
                    },
                    "hero_level": {
                        "region": [20, 600, 80, 24],
                        "numeric": True,
                        "name": "hero_level",
                    },
                },
            ),
            "offline_reward": ScreenROI(
                screen_type="offline_reward",
                gauge_regions={},
                ocr_regions={
                    "reward_amount": {
                        "region": [100, 300, 340, 40],
                        "numeric": True,
                        "name": "reward_amount",
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
                goal_name="collect_offline",
                considerations=[
                    Consideration(
                        name="offline_reward_ready",
                        input_key="has_offline_reward",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=2.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="upgrade_hero",
                considerations=[
                    Consideration(
                        name="enough_resources",
                        input_key="main_resource_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.5,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="prestige_check",
                considerations=[
                    Consideration(
                        name="prestige_available",
                        input_key="can_prestige",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.5,
                    ),
                    Consideration(
                        name="high_progress",
                        input_key="prestige_progress_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.8,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="auto_progress",
                considerations=[
                    Consideration(
                        name="no_offline_reward",
                        input_key="has_offline_reward",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        invert=True,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="buy_boost",
                considerations=[
                    Consideration(
                        name="has_premium",
                        input_key="premium_currency_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.4,
                        weight=1.0,
                    ),
                    Consideration(
                        name="slow_progress",
                        input_key="auto_speed",
                        curve_type=CurveType.INVERSE,
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
                name="collect_offline_reward",
                cost=1.0,
                preconditions={"has_offline_reward": True},
                effects={
                    "has_offline_reward": False,
                    "main_resource": lambda r: (r or 0) + 10000,
                },
                required_screen="offline_reward",
            ),
            GOAPAction(
                name="upgrade",
                cost=2.0,
                preconditions={
                    "main_resource": lambda r: r is not None and r >= 100,
                    "screen_type": "upgrade",
                },
                effects={
                    "main_resource": lambda r: (r or 0) - 100,
                    "hero_level": lambda l: (l or 0) + 1,
                },
                required_screen="upgrade",
            ),
            GOAPAction(
                name="check_prestige",
                cost=2.0,
                preconditions={"can_prestige": True},
                effects={
                    "prestige_points": lambda p: (p or 0) + 1,
                    "hero_level": 0,
                    "main_resource": 0,
                },
                required_screen="prestige",
            ),
            GOAPAction(
                name="buy_speed_boost",
                cost=3.0,
                preconditions={
                    "premium_currency": lambda c: c is not None and c >= 10,
                    "screen_type": "shop",
                },
                effects={
                    "premium_currency": lambda c: (c or 0) - 10,
                    "auto_speed": lambda s: min(10.0, (s or 1.0) * 2.0),
                },
                required_screen="shop",
            ),
        ]

    # ------------------------------------------------------------------
    # Interrupt rules
    # ------------------------------------------------------------------

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "offline_reward_ready",
                "condition": lambda ws: bool(ws.props.get("has_offline_reward")),
                "goal_name": "collect_offline",
                "priority": 8.0,
            },
            {
                "name": "prestige_available",
                "condition": lambda ws: bool(ws.props.get("can_prestige")),
                "goal_name": "prestige_check",
                "priority": 6.0,
            },
        ]
