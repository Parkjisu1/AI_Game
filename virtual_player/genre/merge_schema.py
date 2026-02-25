"""
MergeSchema — Merge Genre Configuration
=========================================
Concepts, ROIs, goals, actions, and interrupt rules for Merge games.
Focus: board management, piece merging, order fulfillment, energy.
No HP/MP gauges — board state analysis is primary.
"""

from typing import Dict, List

from ..perception.region_registry import ScreenROI
from ..reasoning.goap_planner import GOAPAction
from ..reasoning.utility_scorer import Consideration, CurveType, GoalScorer
from .schema import GenreConcept, GenreSchema


class MergeSchema(GenreSchema):
    """Genre schema for Merge games."""

    @property
    def genre_key(self) -> str:
        return "merge"

    @property
    def genre_name(self) -> str:
        return "Merge"

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "board_state": GenreConcept(
                name="board_state", category="special",
                description="Current board occupancy and highest piece level",
                is_required=True,
            ),
            "highest_piece": GenreConcept(
                name="highest_piece", category="stat",
                description="Tier/level of the highest piece on the board",
                is_required=True,
            ),
            "merge_count": GenreConcept(
                name="merge_count", category="stat",
                description="Number of merges performed in the session",
                is_required=False,
            ),
            "order_slots": GenreConcept(
                name="order_slots", category="resource",
                description="Number of active order slots available",
                is_required=False,
            ),
            "energy": GenreConcept(
                name="energy", category="resource",
                description="Energy or action points for board actions",
                is_required=False,
            ),
            "coins": GenreConcept(
                name="coins", category="resource",
                description="Soft currency earned from orders and merges",
                is_required=True,
            ),
        }

    # ------------------------------------------------------------------
    # Screen types
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "game_board": "Main merge board screen",
            "orders": "Active orders / request panel",
            "shop": "Piece shop and special items",
            "inventory": "Inventory / storage for extra pieces",
        }

    # ------------------------------------------------------------------
    # Default screen ROIs
    # ------------------------------------------------------------------

    def get_default_screen_rois(self) -> Dict[str, ScreenROI]:
        return {
            "game_board": ScreenROI(
                screen_type="game_board",
                gauge_regions={},
                ocr_regions={
                    "coins": {
                        "region": [20, 20, 200, 28],
                        "numeric": True,
                        "name": "coins",
                    },
                    "energy": {
                        "region": [300, 20, 120, 28],
                        "numeric": True,
                        "name": "energy",
                    },
                    "highest_piece": {
                        "region": [400, 700, 80, 28],
                        "numeric": True,
                        "name": "highest_piece",
                    },
                },
            ),
            "orders": ScreenROI(
                screen_type="orders",
                gauge_regions={},
                ocr_regions={
                    "order_count": {
                        "region": [20, 100, 60, 24],
                        "numeric": True,
                        "name": "order_count",
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
                goal_name="merge_highest",
                considerations=[
                    Consideration(
                        name="board_has_pairs",
                        input_key="mergeable_pairs",
                        curve_type=CurveType.SIGMOID,
                        k=5.0, mid=2.0,
                        weight=2.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="fill_orders",
                considerations=[
                    Consideration(
                        name="has_orders",
                        input_key="active_order_count",
                        curve_type=CurveType.STEP,
                        threshold=0.5,
                        weight=1.5,
                    ),
                    Consideration(
                        name="can_fulfill",
                        input_key="fulfillable_order_pct",
                        curve_type=CurveType.SIGMOID,
                        k=10.0, mid=0.3,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="clear_board",
                considerations=[
                    Consideration(
                        name="board_full",
                        input_key="board_fill_pct",
                        curve_type=CurveType.SIGMOID,
                        k=15.0, mid=0.85,
                        weight=2.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="discover_new",
                considerations=[
                    Consideration(
                        name="high_piece_available",
                        input_key="highest_piece",
                        curve_type=CurveType.LINEAR,
                        m=0.1, b=0.0,
                        weight=1.0,
                    ),
                ],
            ),
            GoalScorer(
                goal_name="earn_coins",
                considerations=[
                    Consideration(
                        name="low_coins",
                        input_key="coin_pct",
                        curve_type=CurveType.INVERSE,
                        weight=1.0,
                    ),
                    Consideration(
                        name="has_orders",
                        input_key="active_order_count",
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
                name="merge_pieces",
                cost=1.0,
                preconditions={
                    "mergeable_pairs": lambda p: p is not None and p >= 1,
                    "screen_type": "game_board",
                },
                effects={
                    "mergeable_pairs": lambda p: max(0, (p or 0) - 1),
                    "highest_piece": lambda h: (h or 0) + 1,
                    "merge_count": lambda c: (c or 0) + 1,
                },
                required_screen="game_board",
            ),
            GOAPAction(
                name="complete_order",
                cost=2.0,
                preconditions={
                    "fulfillable_order_pct": lambda p: p is not None and p > 0,
                    "screen_type": "orders",
                },
                effects={
                    "active_order_count": lambda c: max(0, (c or 0) - 1),
                    "coins": lambda c: (c or 0) + 200,
                    "fulfillable_order_pct": lambda p: max(0.0, (p or 0) - 0.33),
                },
                required_screen="orders",
            ),
            GOAPAction(
                name="buy_piece",
                cost=3.0,
                preconditions={
                    "coins": lambda c: c is not None and c >= 50,
                    "screen_type": "shop",
                },
                effects={
                    "coins": lambda c: (c or 0) - 50,
                    "mergeable_pairs": lambda p: (p or 0) + 1,
                },
                required_screen="shop",
            ),
            GOAPAction(
                name="clear_space",
                cost=2.0,
                preconditions={
                    "board_fill_pct": lambda p: p is not None and p >= 0.8,
                    "screen_type": "game_board",
                },
                effects={
                    "board_fill_pct": lambda p: max(0.0, (p or 1.0) - 0.15),
                },
                required_screen="game_board",
            ),
        ]

    # ------------------------------------------------------------------
    # Interrupt rules
    # ------------------------------------------------------------------

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "board_full",
                "condition": lambda ws: (ws.props.get("board_fill_pct") or 0.0) >= 0.95,
                "goal_name": "clear_board",
                "priority": 9.0,
            },
            {
                "name": "order_expiring",
                "condition": lambda ws: bool(ws.props.get("order_expiring_soon")),
                "goal_name": "fill_orders",
                "priority": 7.0,
            },
        ]
