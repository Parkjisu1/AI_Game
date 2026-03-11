"""
Tower Defense 장르 프로필
=========================
Plants vs Zombies, Arknights, Kingdom Rush 등.
"""

from .base import ActionCategory, GenreProfile


def create_tower_defense_profile() -> GenreProfile:
    return GenreProfile(
        genre_id="tower_defense",
        genre_name="Tower Defense",

        action_mix=ActionCategory(
            navigate=0.05,
            select=0.15,
            place=0.30,      # 타워 배치가 핵심
            activate=0.15,    # 스킬/능력 사용
            wait=0.10,        # 웨이브 간 대기
            decide=0.15,      # 배치 위치/업그레이드 판단
            respond=0.10,
        ),

        screen_flow={
            "lobby": ["stage_select", "shop", "hero_select"],
            "stage_select": ["gameplay", "lobby"],
            "gameplay": ["win", "fail", "pause"],
            "win": ["lobby", "stage_select"],
            "fail": ["lobby", "gameplay"],
            "pause": ["gameplay", "lobby"],
            "shop": ["lobby"],
            "hero_select": ["lobby"],
        },

        perception_hints=(
            "This is a tower defense game. "
            "Look for: path/lane where enemies walk, "
            "tower placement spots (highlighted or empty), "
            "tower selection bar at bottom, "
            "wave counter, resource/currency counter, "
            "enemy health bars, active skill buttons."
        ),

        never_do=[
            "purchase premium currency",
            "sell high-level towers during active wave",
            "place towers blocking essential paths",
            "skip tutorial tower placements",
        ],

        always_do=[
            "place towers at chokepoints first",
            "upgrade existing towers before placing new ones",
            "use active skills on tough enemies",
            "collect idle rewards between levels",
            "close popup/ad dialogs immediately",
        ],

        is_realtime=True,
        input_types=["tap", "drag"],
        typical_session_minutes=10,
        typical_level_seconds=180,
    )
