"""
CasualSchema -- Casual Genre Configuration
==========================================
Concepts, ROIs, goals, actions, and interrupt rules for Casual games.
Focus: level progression, score maximization, lives management, booster usage,
daily reward collection, and star/coin earning.
"""

from typing import Dict, List

from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class CasualSchema(GenreSchema):
    """Genre schema for Casual games."""

    @property
    def genre_key(self) -> str:
        return "casual"

    @property
    def genre_name(self) -> str:
        return "Casual"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "score": GenreConcept(
                name="score", category="resource",
                description="Current in-level or cumulative score",
                is_required=True,
            ),
            "lives": GenreConcept(
                name="lives", category="resource",
                description="Hearts or lives available to play levels",
                is_required=True,
            ),
            "level": GenreConcept(
                name="level", category="stat",
                description="Current level or stage number in the progression",
                is_required=True,
            ),
            "coins": GenreConcept(
                name="coins", category="resource",
                description="Soft currency earned from gameplay and rewards",
                is_required=False,
            ),
            "boosters": GenreConcept(
                name="boosters", category="resource",
                description="Power-up items that assist during level play",
                is_required=False,
            ),
            "stars": GenreConcept(
                name="stars", category="stat",
                description="Stars earned per level (0–3 rating)",
                is_required=False,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "lobby": "Main level select / map progression screen",
            "gameplay": "Active in-level gameplay screen",
            "win_screen": "Level complete / victory result screen",
            "fail_screen": "Level failed / game over screen",
            "shop": "In-game shop for boosters, coins, and lives",
            "booster_select": "Pre-level booster selection screen",
            "daily_reward": "Daily login reward claim popup",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "gameplay": ScreenROI(
                screen_type="gameplay",
                gauge_regions={},
                ocr_regions={
                    "score": {
                        "region": [200, 20, 240, 32],
                        "numeric": True,
                        "name": "score",
                    },
                    "lives": {
                        "region": [20, 20, 100, 32],
                        "numeric": True,
                        "name": "lives",
                    },
                },
            ),
            "lobby": ScreenROI(
                screen_type="lobby",
                gauge_regions={},
                ocr_regions={
                    "level": {
                        "region": [160, 60, 200, 36],
                        "numeric": True,
                        "name": "level",
                    },
                    "coins": {
                        "region": [20, 30, 180, 28],
                        "numeric": True,
                        "name": "coins",
                    },
                    "lives": {
                        "region": [380, 30, 120, 28],
                        "numeric": True,
                        "name": "lives",
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
                goal_name="play_level",
                considerations=[
                    Consideration(
                        name="has_lives",
                        input_key="lives_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.1,
                        weight=2.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="use_booster",
                considerations=[
                    Consideration(
                        name="has_boosters",
                        input_key="boosters_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.1,
                        weight=1.0,
                    ),
                    Consideration(
                        name="has_lives",
                        input_key="lives_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.1,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="earn_stars",
                considerations=[
                    Consideration(
                        name="has_lives",
                        input_key="lives_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.2,
                        weight=1.5,
                    ),
                    Consideration(
                        name="low_stars",
                        input_key="stars_pct",
                        curve_type=CurveType.INVERSE,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="collect_daily",
                considerations=[
                    Consideration(
                        name="daily_reward_ready",
                        input_key="has_daily_reward",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=2.0,
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
                name="start_level",
                cost=1.0,
                preconditions={
                    "lives": lambda l: l is not None and l >= 1,
                    "screen_type": "lobby",
                },
                effects={
                    "lives": lambda l: (l or 1) - 1,
                    "screen_type": "gameplay",
                },
                required_screen="lobby",
            ),
            GOAPAction(
                name="use_booster",
                cost=1.5,
                preconditions={
                    "boosters": lambda b: b is not None and b >= 1,
                    "screen_type": "booster_select",
                },
                effects={
                    "boosters": lambda b: (b or 1) - 1,
                    "score": lambda s: (s or 0) + 500,
                },
                required_screen="booster_select",
            ),
            GOAPAction(
                name="retry_level",
                cost=2.0,
                preconditions={
                    "lives": lambda l: l is not None and l >= 1,
                    "screen_type": "fail_screen",
                },
                effects={
                    "lives": lambda l: (l or 1) - 1,
                    "screen_type": "gameplay",
                },
                required_screen="fail_screen",
            ),
            GOAPAction(
                name="claim_reward",
                cost=1.0,
                preconditions={"has_daily_reward": True},
                effects={
                    "has_daily_reward": False,
                    "coins": lambda c: (c or 0) + 100,
                },
                required_screen="daily_reward",
            ),
            GOAPAction(
                name="buy_lives",
                cost=2.0,
                preconditions={
                    "coins": lambda c: c is not None and c >= 50,
                    "lives": lambda l: l is not None and l <= 0,
                    "screen_type": "shop",
                },
                effects={
                    "coins": lambda c: (c or 0) - 50,
                    "lives": lambda l: (l or 0) + 5,
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
                "name": "lives_depleted",
                "condition": lambda ws: (ws.props.get("lives") or 1) <= 0,
                "goal_name": "buy_lives",
                "priority": 9.0,
            },
            {
                "name": "ad_available",
                "condition": lambda ws: bool(ws.props.get("ad_reward_available")),
                "goal_name": "collect_daily",
                "priority": 5.0,
            },
        ]

    # ------------------------------------------------------------------
    # Exploration hints
    # ------------------------------------------------------------------

    def get_exploration_hints(self) -> Dict[str, list]:
        return {
            "priority_screens": ["lobby", "gameplay"],
            "safe_screens": ["lobby", "win_screen", "daily_reward"],
            "danger_screens": ["shop"],
            "ocr_keywords": [
                "play", "start", "level", "score", "lives", "heart",
                "booster", "star", "coin", "daily", "reward", "bonus",
                "시작", "레벨", "점수", "라이프", "하트", "부스터",
                "별", "코인", "일일", "보상",
            ],
        }
