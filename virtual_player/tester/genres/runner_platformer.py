"""
Runner/Platformer 장르 프로필
==============================
Subway Surfers, Temple Run, Geometry Dash 등.
"""

from .base import ActionCategory, GenreProfile


def create_runner_platformer_profile() -> GenreProfile:
    return GenreProfile(
        genre_id="runner_platformer",
        genre_name="Runner / Platformer",

        action_mix=ActionCategory(
            navigate=0.05,
            select=0.05,
            place=0.00,
            activate=0.10,
            wait=0.00,
            decide=0.10,
            respond=0.70,   # 실시간 반응이 핵심
        ),

        screen_flow={
            "lobby": ["gameplay", "shop", "character_select"],
            "gameplay": ["win", "fail", "pause"],
            "win": ["lobby", "gameplay"],
            "fail": ["lobby", "gameplay"],
            "pause": ["gameplay", "lobby"],
            "shop": ["lobby"],
            "character_select": ["lobby"],
        },

        perception_hints=(
            "This is a runner/platformer game. "
            "Look for: character running forward, obstacles, "
            "coins/collectibles, score counter, "
            "swipe/tap indicators, speed/distance meter."
        ),

        never_do=[
            "purchase premium currency",
            "tap install buttons in ads",
            "pause during active gameplay (wastes run)",
        ],

        always_do=[
            "react quickly to obstacles (swipe/tap)",
            "collect power-ups when safe",
            "revive once per run if free option available",
            "close ads via X button",
        ],

        is_realtime=True,
        input_types=["tap", "swipe"],
        typical_session_minutes=3,
        typical_level_seconds=45,
    )
