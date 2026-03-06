"""
PuzzleSchema -- Puzzle Genre Configuration
============================================
Defines concepts, actions, goals, and screen types for puzzle games
(match-3, parking puzzles, tile matching, etc.).
"""

from typing import Dict, List

from .schema import GenreConcept, GenreSchema


class PuzzleSchema(GenreSchema):
    """Genre schema for puzzle games."""

    @property
    def genre_key(self) -> str:
        return "puzzle"

    @property
    def genre_name(self) -> str:
        return "Puzzle"

    def get_concepts(self) -> Dict[str, GenreConcept]:
        return {
            "board_state": GenreConcept(
                name="board_state", category="special",
                description="Current board/grid configuration",
            ),
            "holder": GenreConcept(
                name="holder", category="special",
                description="Holding area for selected items",
                is_required=False,
            ),
            "score": GenreConcept(
                name="score", category="resource",
                description="Current level score",
            ),
            "moves": GenreConcept(
                name="moves", category="resource",
                description="Remaining moves/time",
                is_required=False,
            ),
            "lives": GenreConcept(
                name="lives", category="resource",
                description="Lives/hearts remaining",
            ),
            "match_count": GenreConcept(
                name="match_count", category="stat",
                description="Number of successful matches",
            ),
            "level": GenreConcept(
                name="level", category="stat",
                description="Current level number",
            ),
            "stars": GenreConcept(
                name="stars", category="stat",
                description="Stars earned this level",
                is_required=False,
            ),
            "boosters": GenreConcept(
                name="boosters", category="resource",
                description="Available power-ups/boosters",
                is_required=False,
            ),
        }

    def get_default_screen_rois(self) -> Dict:
        return {}  # Puzzle ROIs vary too much to have useful defaults

    def get_goal_templates(self) -> List:
        return []  # Puzzle goals are level-objective-based

    def get_action_templates(self) -> List:
        return []  # Puzzle actions are board-interaction-based

    def get_interrupt_rules(self) -> List[dict]:
        return [
            {
                "name": "lives_depleted",
                "condition": lambda ws: ws.get("lives", 5) <= 0,
                "goal_name": "wait_for_lives",
                "priority": 100,
            },
        ]

    def get_screen_types(self) -> Dict[str, str]:
        return {
            "lobby": "Main menu / level select",
            "gameplay": "Active puzzle board",
            "win": "Level complete screen",
            "fail": "Level failed screen",
            "shop": "In-game shop",
            "settings": "Settings menu",
            "ad": "Advertisement overlay",
            "popup": "Popup dialog",
            "loading": "Loading screen",
        }

    def get_board_config(self, game_type: str = "generic") -> dict:
        """Return default board configuration for puzzle board reading.

        Returned dict is suitable for BoardReader.read_board() and
        BoardReader.board_to_screen_coords().

        game_type: "carmatch" | "match3" | "generic"
        """
        if game_type == "carmatch":
            return {
                "board_rect": (40, 200, 1000, 1180),   # (x, y, w, h) CarMatch board area
                "rows": 8,
                "cols": 7,
                "holder_rect": (40, 1400, 1000, 200),  # holder strip below board
                "holder_slots": 7,
            }
        elif game_type == "match3":
            return {
                "board_rect": (0, 300, 1080, 1080),
                "rows": 9,
                "cols": 9,
                "holder_rect": None,
                "holder_slots": 0,
            }
        else:
            return {
                "board_rect": (0, 200, 1080, 1300),
                "rows": 8,
                "cols": 8,
                "holder_rect": None,
                "holder_slots": 0,
            }

    def get_exploration_hints(self) -> Dict[str, list]:
        return {
            "priority_screens": ["lobby", "gameplay"],
            "safe_screens": ["lobby", "settings"],
            "danger_screens": ["shop"],
            "ocr_keywords": [
                "play", "start", "level", "score", "lives", "heart",
                "보석", "다이아", "시작", "레벨", "점수",
            ],
        }
