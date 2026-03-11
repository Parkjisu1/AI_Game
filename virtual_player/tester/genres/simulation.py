"""
Simulation / Management 장르 프로필
====================================
SimCity, Hay Day, Township, Merge 게임 등.
"""

from .base import ActionCategory, GenreProfile


def create_simulation_profile() -> GenreProfile:
    return GenreProfile(
        genre_id="simulation",
        genre_name="Simulation / Management",

        action_mix=ActionCategory(
            navigate=0.15,     # 맵/건물 간 이동
            select=0.15,       # 건물/아이템 선택
            place=0.15,        # 건물 배치, merge
            activate=0.05,
            wait=0.15,         # 타이머/건설 대기
            decide=0.25,       # 리소스 관리 판단
            respond=0.10,
        ),

        screen_flow={
            "main": ["shop", "inventory", "quest", "build_menu", "map"],
            "shop": ["main"],
            "inventory": ["main"],
            "quest": ["main"],
            "build_menu": ["main"],
            "map": ["main", "level"],
            "level": ["win", "fail", "main"],
            "win": ["main"],
            "fail": ["main"],
        },

        perception_hints=(
            "This is a simulation/management game. "
            "Look for: buildings/structures on a map, "
            "resource counters (coins, gems, materials), "
            "construction timers, quest indicators, "
            "merge board (if merge game), "
            "bottom menu tabs for navigation."
        ),

        never_do=[
            "purchase premium currency",
            "speed up timers with gems (unless free)",
            "delete/sell buildings without checking value",
            "ignore quest notifications",
        ],

        always_do=[
            "collect produced resources from buildings",
            "start new production cycles",
            "claim completed quests",
            "collect daily login rewards",
            "close event popups via X",
        ],

        is_realtime=False,
        input_types=["tap", "drag", "pinch"],
        typical_session_minutes=5,
        typical_level_seconds=30,
    )
