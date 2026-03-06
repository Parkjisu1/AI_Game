"""
Idle RPG 장르 프로필
=====================
Ash & Veil, AFK Arena, Idle Heroes 등 방치형 RPG 공통 규칙.
"""

from .base import ActionCategory, GenreProfile


def create_idle_rpg_profile() -> GenreProfile:
    return GenreProfile(
        genre_id="idle_rpg",
        genre_name="Idle RPG",

        action_mix=ActionCategory(
            navigate=0.20,
            select=0.10,
            place=0.00,
            activate=0.05,
            wait=0.30,
            decide=0.20,
            respond=0.15,
        ),

        screen_flow={
            "main": ["battle", "shop", "hero_list", "gacha", "quest", "setting"],
            "battle": ["battle_result", "main"],
            "battle_result": ["main", "battle"],
            "shop": ["main"],
            "hero_list": ["hero_detail", "main"],
            "hero_detail": ["hero_list"],
            "gacha": ["gacha_result", "main"],
            "gacha_result": ["gacha", "main"],
            "quest": ["main"],
        },

        perception_hints=(
            "This is an idle RPG game. "
            "Look for: hero portraits, battle/auto-battle buttons, "
            "resource counters (gold, gems, stamina), "
            "menu tabs at bottom, quest notifications."
        ),

        never_do=[
            "purchase premium currency with real money",
            "skip tutorial before it completes",
            "sell/discard heroes without checking rarity",
            "spend all stamina at once without checking rewards",
        ],

        always_do=[
            "collect idle rewards when available",
            "claim daily quests/missions",
            "close event popups via X",
            "check for free gacha pulls",
        ],

        is_realtime=False,
        input_types=["tap", "swipe"],
        typical_session_minutes=5,
        typical_level_seconds=30,
    )
