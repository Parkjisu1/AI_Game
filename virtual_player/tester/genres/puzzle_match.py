"""
Puzzle Match 장르 프로필
========================
CarMatch, Candy Crush, Toon Blast 등 퍼즐 매치 계열 공통 규칙.
"""

from .base import ActionCategory, GenreProfile


def create_puzzle_match_profile() -> GenreProfile:
    return GenreProfile(
        genre_id="puzzle_match",
        genre_name="Puzzle Match",

        action_mix=ActionCategory(
            navigate=0.15,
            select=0.40,
            place=0.00,
            activate=0.10,
            wait=0.05,
            decide=0.15,
            respond=0.15,
        ),

        screen_flow={
            "lobby": ["gameplay"],
            "gameplay": ["win", "fail_outofspace", "fail_continue", "ingame_setting"],
            "win": ["lobby"],
            "fail_outofspace": ["fail_continue", "gameplay"],
            "fail_continue": ["fail_result", "gameplay"],
            "fail_result": ["lobby", "gameplay"],
        },

        perception_hints=(
            "This is a puzzle match game. "
            "Look for: game board with colorful objects, "
            "holder/tray at bottom, boosters bar, "
            "score/moves counter at top."
        ),

        never_do=[
            "purchase or spend real currency",
            "tap install/download buttons in ads",
            "use shuffle/rotate unless explicitly allowed",
            "tap objects that are clearly blocked/inactive",
        ],

        always_do=[
            "close popups before gameplay actions",
            "prioritize match completion (2 in holder → find 3rd)",
            "use undo when holder is near full",
            "close ads via X button or back",
        ],

        is_realtime=False,
        input_types=["tap"],
        typical_session_minutes=10,
        typical_level_seconds=90,
    )
