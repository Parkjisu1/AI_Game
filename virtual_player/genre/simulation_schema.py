"""
SimulationSchema -- Simulation Genre Configuration
===================================================
Concepts, ROIs, goals, actions, and interrupt rules for Simulation games.
Focus: population growth, happiness management, infrastructure building,
resource balancing, event responses, and budget control.
"""

from typing import Dict, List

from ..perception.gauge_reader import GaugeProfile
from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class SimulationSchema(GenreSchema):
    """Genre schema for Simulation games."""

    @property
    def genre_key(self) -> str:
        return "simulation"

    @property
    def genre_name(self) -> str:
        return "Simulation"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "population": GenreConcept(
                name="population", category="stat",
                description="Current citizen or unit population count",
                is_required=True,
            ),
            "happiness": GenreConcept(
                name="happiness", category="gauge",
                description="Overall population happiness percentage",
                default_gauge_profile="happiness_bar",
                is_required=False,
            ),
            "resources": GenreConcept(
                name="resources", category="resource",
                description="Primary construction and production resources",
                is_required=True,
            ),
            "buildings": GenreConcept(
                name="buildings", category="stat",
                description="Number of constructed buildings or zones",
                is_required=False,
            ),
            "time_speed": GenreConcept(
                name="time_speed", category="stat",
                description="Simulation time multiplier (1x, 2x, 3x)",
                is_required=False,
            ),
            "budget": GenreConcept(
                name="budget", category="resource",
                description="Available financial budget for city operations",
                is_required=False,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "main_view": "Primary simulation map or city overview",
            "build_menu": "Building placement and construction menu",
            "stats_panel": "Population, happiness, and resource statistics panel",
            "settings": "Game settings and time speed controls",
            "event_popup": "Random event or disaster notification popup",
            "budget_screen": "Budget allocation and tax rate management screen",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "main_view": ScreenROI(
                screen_type="main_view",
                gauge_regions={
                    "happiness_bar": {
                        "region": [20, 60, 280, 16],
                        "profile": "happiness_bar",
                    },
                },
                ocr_regions={
                    "population": {
                        "region": [100, 20, 240, 28],
                        "numeric": True,
                        "name": "population",
                    },
                    "resources": {
                        "region": [360, 20, 200, 28],
                        "numeric": True,
                        "name": "resources",
                    },
                    "budget": {
                        "region": [580, 20, 180, 28],
                        "numeric": True,
                        "name": "budget",
                    },
                },
            ),
            "budget_screen": ScreenROI(
                screen_type="budget_screen",
                gauge_regions={},
                ocr_regions={
                    "budget": {
                        "region": [80, 100, 300, 32],
                        "numeric": True,
                        "name": "budget",
                    },
                    "income": {
                        "region": [80, 145, 260, 28],
                        "numeric": True,
                        "name": "income",
                    },
                    "expenses": {
                        "region": [80, 185, 260, 28],
                        "numeric": True,
                        "name": "expenses",
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
                name="happiness_bar",
                hsv_lower=(35, 80, 80),
                hsv_upper=(85, 255, 255),
                color_rgb=(0, 200, 0),
            ),
            # Yellow: moderate happiness warning
            GaugeProfile(
                name="happiness_bar_warning",
                hsv_lower=(20, 80, 80),
                hsv_upper=(35, 255, 255),
                color_rgb=(200, 200, 0),
            ),
            # Red: critical happiness alert
            GaugeProfile(
                name="happiness_bar_critical",
                hsv_lower=(0, 80, 80),
                hsv_upper=(10, 255, 255),
                color_rgb=(200, 0, 0),
                hsv_lower2=(170, 80, 80),
                hsv_upper2=(180, 255, 255),
            ),
        ]

    # ------------------------------------------------------------------
    # Goal scorers
    # ------------------------------------------------------------------

    def get_goal_templates(self) -> List[GoalScorer]:
        return [
            GoalScorer(
                goal_name="grow_population",
                considerations=[
                    Consideration(
                        name="enough_resources",
                        input_key="resources_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.4,
                        weight=1.5,
                    ),
                    Consideration(
                        name="happy_citizens",
                        input_key="happiness_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.4,
                        weight=1.0,
                    ),
                    Consideration(
                        name="has_budget",
                        input_key="budget_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.2,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="improve_happiness",
                considerations=[
                    Consideration(
                        name="low_happiness",
                        input_key="happiness_pct",
                        curve_type=CurveType.INVERSE,
                        weight=2.0,
                    ),
                    Consideration(
                        name="has_resources",
                        input_key="resources_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.3,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="build_infrastructure",
                considerations=[
                    Consideration(
                        name="enough_resources",
                        input_key="resources_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.5,
                        weight=1.0,
                    ),
                    Consideration(
                        name="positive_budget",
                        input_key="budget_pct",
                        curve_type=CurveType.STEP,
                        threshold=0.3,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="manage_budget",
                considerations=[
                    Consideration(
                        name="budget_low",
                        input_key="budget_pct",
                        curve_type=CurveType.INVERSE,
                        weight=1.5,
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
                name="build_structure",
                cost=2.0,
                preconditions={
                    "resources": lambda r: r is not None and r >= 150,
                    "budget": lambda b: b is not None and b >= 0,
                    "screen_type": "build_menu",
                },
                effects={
                    "resources": lambda r: (r or 0) - 150,
                    "buildings": lambda b: (b or 0) + 1,
                    "population": lambda p: (p or 0) + 20,
                },
                required_screen="build_menu",
            ),
            GOAPAction(
                name="adjust_taxes",
                cost=1.5,
                preconditions={
                    "screen_type": "budget_screen",
                    "budget": lambda b: b is not None and b < 0,
                },
                effects={
                    "budget": lambda b: (b or 0) + 500,
                    "happiness": lambda h: max(0.0, (h or 0.5) - 0.05),
                },
                required_screen="budget_screen",
            ),
            GOAPAction(
                name="respond_to_event",
                cost=1.0,
                preconditions={"has_pending_event": True},
                effects={
                    "has_pending_event": False,
                    "happiness": lambda h: min(1.0, (h or 0.5) + 0.1),
                },
                required_screen="event_popup",
            ),
            GOAPAction(
                name="upgrade_service",
                cost=3.0,
                preconditions={
                    "resources": lambda r: r is not None and r >= 300,
                    "screen_type": "build_menu",
                },
                effects={
                    "resources": lambda r: (r or 0) - 300,
                    "happiness": lambda h: min(1.0, (h or 0.5) + 0.08),
                    "population": lambda p: (p or 0) + 10,
                },
                required_screen="build_menu",
            ),
        ]

    # ------------------------------------------------------------------
    # Interrupt rules
    # ------------------------------------------------------------------

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "happiness_critical",
                "condition": lambda ws: (ws.props.get("happiness_pct") or 1.0) < 0.2,
                "goal_name": "improve_happiness",
                "priority": 9.0,
            },
            {
                "name": "budget_negative",
                "condition": lambda ws: (ws.props.get("budget") or 0) < 0,
                "goal_name": "manage_budget",
                "priority": 8.0,
            },
        ]
