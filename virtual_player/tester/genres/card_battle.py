"""
Card Battle 장르 프로필
========================
Hearthstone, Clash Royale, Yu-Gi-Oh 등.
"""

from .base import ActionCategory, GenreProfile


def create_card_battle_profile() -> GenreProfile:
    return GenreProfile(
        genre_id="card_battle",
        genre_name="Card Battle",

        action_mix=ActionCategory(
            navigate=0.10,
            select=0.25,      # 카드 선택
            place=0.20,       # 카드 배치/사용
            activate=0.05,
            wait=0.05,        # 상대 턴 대기
            decide=0.25,      # 전략적 판단 (어떤 카드를 언제)
            respond=0.10,
        ),

        screen_flow={
            "lobby": ["deck_builder", "shop", "gameplay", "matchmaking"],
            "matchmaking": ["gameplay", "lobby"],
            "gameplay": ["win", "fail"],
            "win": ["lobby", "reward"],
            "fail": ["lobby"],
            "reward": ["lobby"],
            "deck_builder": ["lobby"],
            "shop": ["lobby"],
        },

        perception_hints=(
            "This is a card battle game. "
            "Look for: hand of cards at bottom, "
            "board/field with played cards, "
            "mana/energy counter, "
            "opponent's cards/field at top, "
            "end turn button, hero portrait/HP."
        ),

        never_do=[
            "purchase card packs with real money",
            "disenchant/destroy rare cards",
            "play cards without checking mana cost",
            "concede before turn 5",
        ],

        always_do=[
            "play cards that fit current mana",
            "prioritize removing high-threat enemy cards",
            "end turn when no playable cards remain",
            "collect daily rewards",
            "close ads/popups via X",
        ],

        is_realtime=False,
        input_types=["tap", "drag"],
        typical_session_minutes=10,
        typical_level_seconds=120,
    )
