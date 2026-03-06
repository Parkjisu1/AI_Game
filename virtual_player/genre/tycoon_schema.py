"""
TycoonSchema -- Tycoon Genre Configuration
==========================================
Concepts, ROIs, goals, actions, and interrupt rules for Tycoon games.
Focus: revenue generation, customer flow, building upgrades, staff management,
satisfaction maintenance, and offline income collection.
"""

from typing import Dict, List

from ..perception.gauge_reader import GaugeProfile
from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class TycoonSchema(GenreSchema):
    """Genre schema for Tycoon games."""

    @property
    def genre_key(self) -> str:
        return "tycoon"

    @property
    def genre_name(self) -> str:
        return "Tycoon"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "revenue": GenreConcept(
                name="revenue", category="resource",
                description="Primary earned income / cash accumulation",
                is_required=True,
            ),
            "customers": GenreConcept(
                name="customers", category="stat",
                description="Current number of customers visiting the business",
                is_required=True,
            ),
            "buildings": GenreConcept(
                name="buildings", category="stat",
                description="Number of owned or upgraded buildings/facilities",
                is_required=False,
            ),
            "staff": GenreConcept(
                name="staff", category="stat",
                description="Number of hired staff members",
                is_required=False,
            ),
            "satisfaction": GenreConcept(
                name="satisfaction", category="gauge",
                description="Customer satisfaction percentage",
                default_gauge_profile="satisfaction_bar",
                is_required=False,
            ),
            "premium_currency": GenreConcept(
                name="premium_currency", category="resource",
                description="Hard currency used for instant upgrades and special hires",
                is_required=False,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "main_business": "Primary business / shop floor view with active customers",
            "upgrade_panel": "Building or facility upgrade selection screen",
            "hire_staff": "Staff hiring and management panel",
            "research": "Technology or skill research tree screen",
            "shop": "In-game shop for purchasing boosters and items",
            "stats_overview": "Business statistics and performance summary",
            "offline_reward": "Offline income collection popup",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "main_business": ScreenROI(
                screen_type="main_business",
                gauge_regions={
                    "satisfaction_bar": {
                        "region": [20, 80, 300, 18],
                        "profile": "satisfaction_bar",
                    },
                },
                ocr_regions={
                    "revenue": {
                        "region": [100, 20, 340, 30],
                        "numeric": True,
                        "name": "revenue",
                    },
                    "customers": {
                        "region": [20, 55, 140, 24],
                        "numeric": True,
                        "name": "customers",
                    },
                },
            ),
            "stats_overview": ScreenROI(
                screen_type="stats_overview",
                gauge_regions={},
                ocr_regions={
                    "revenue": {
                        "region": [80, 120, 300, 28],
                        "numeric": True,
                        "name": "revenue",
                    },
                    "customers": {
                        "region": [80, 160, 240, 28],
                        "numeric": True,
                        "name": "customers",
                    },
                    "staff": {
                        "region": [80, 200, 200, 28],
                        "numeric": True,
                        "name": "staff",
                    },
                    "buildings": {
                        "region": [80, 240, 200, 28],
                        "numeric": True,
                        "name": "buildings",
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
                name="satisfaction_bar",
                hsv_lower=(35, 80, 80),
                hsv_upper=(85, 255, 255),
                color_rgb=(0, 200, 80),
            ),
        ]

    # ------------------------------------------------------------------
    # Goal scorers
    # ------------------------------------------------------------------

    def get_goal_templates(self) -> List[GoalScorer]:
        return [
            GoalScorer(
                goal_name="expand_business",
                considerations=[
                    Consideration(
                        name="enough_revenue",
                        input_key="revenue_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.6,
                        weight=1.5,
                    ),
                    Consideration(
                        name="satisfied_customers",
                        input_key="satisfaction_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.4,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="hire_employees",
                considerations=[
                    Consideration(
                        name="enough_revenue",
                        input_key="revenue_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.4,
                        weight=1.0,
                    ),
                    Consideration(
                        name="low_staff",
                        input_key="staff_pct",
                        curve_type=CurveType.INVERSE,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="research_upgrade",
                considerations=[
                    Consideration(
                        name="has_premium",
                        input_key="premium_currency_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.3,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="collect_revenue",
                considerations=[
                    Consideration(
                        name="revenue_full",
                        input_key="revenue_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.9,
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
                name="upgrade_building",
                cost=2.0,
                preconditions={
                    "revenue": lambda r: r is not None and r >= 200,
                    "screen_type": "upgrade_panel",
                },
                effects={
                    "revenue": lambda r: (r or 0) - 200,
                    "buildings": lambda b: (b or 0) + 1,
                    "customers": lambda c: (c or 0) + 10,
                },
                required_screen="upgrade_panel",
            ),
            GOAPAction(
                name="hire_staff",
                cost=2.0,
                preconditions={
                    "revenue": lambda r: r is not None and r >= 100,
                    "screen_type": "hire_staff",
                },
                effects={
                    "revenue": lambda r: (r or 0) - 100,
                    "staff": lambda s: (s or 0) + 1,
                    "satisfaction": lambda s: min(1.0, (s or 0.5) + 0.05),
                },
                required_screen="hire_staff",
            ),
            GOAPAction(
                name="research_tech",
                cost=3.0,
                preconditions={
                    "premium_currency": lambda c: c is not None and c >= 20,
                    "screen_type": "research",
                },
                effects={
                    "premium_currency": lambda c: (c or 0) - 20,
                    "customers": lambda c: (c or 0) + 5,
                },
                required_screen="research",
            ),
            GOAPAction(
                name="collect_offline",
                cost=1.0,
                preconditions={"has_offline_reward": True},
                effects={
                    "has_offline_reward": False,
                    "revenue": lambda r: (r or 0) + 5000,
                },
                required_screen="offline_reward",
            ),
        ]

    # ------------------------------------------------------------------
    # Interrupt rules
    # ------------------------------------------------------------------

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "revenue_full",
                "condition": lambda ws: (ws.props.get("revenue_pct") or 0.0) >= 0.95,
                "goal_name": "collect_revenue",
                "priority": 9.0,
            },
            {
                "name": "satisfaction_low",
                "condition": lambda ws: (ws.props.get("satisfaction_pct") or 1.0) < 0.25,
                "goal_name": "hire_employees",
                "priority": 7.0,
            },
        ]
