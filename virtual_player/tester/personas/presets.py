"""
Persona Presets — 기본 플레이어 프리셋
=======================================
"""

from typing import Dict, List

from .base import PlayerProfile

# 프리셋 레지스트리
_PRESETS: Dict[str, PlayerProfile] = {}


def _register_builtins():
    """내장 프리셋 등록."""
    _PRESETS["casual_f2p"] = PlayerProfile(
        persona_id="casual_f2p",
        persona_name="Casual F2P Player",
        session_duration_min=5,
        sessions_per_day=3,
        retry_on_fail=1,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=3,
        look_ahead_turns=1,
        tap_precision_px=30,
        decision_speed_sec=2.0,
        booster_save_tendency=0.3,
        quit_after_consecutive_fails=3,
        quit_after_minutes=15,
    )

    _PRESETS["mid_dolphin"] = PlayerProfile(
        persona_id="mid_dolphin",
        persona_name="Mid-spending Dolphin",
        session_duration_min=15,
        sessions_per_day=5,
        retry_on_fail=3,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=True,
        watch_ads=True,
        max_ads_per_session=5,
        look_ahead_turns=2,
        tap_precision_px=20,
        decision_speed_sec=1.5,
        booster_save_tendency=0.5,
        quit_after_consecutive_fails=5,
        quit_after_minutes=30,
    )

    _PRESETS["hardcore_whale"] = PlayerProfile(
        persona_id="hardcore_whale",
        persona_name="Hardcore Whale",
        session_duration_min=30,
        sessions_per_day=8,
        retry_on_fail=5,
        holder_worry_at=5,
        holder_use_booster_at=6,
        holder_panic_at=7,
        will_purchase=True,
        watch_ads=False,
        max_ads_per_session=0,
        look_ahead_turns=3,
        tap_precision_px=10,
        decision_speed_sec=1.0,
        booster_save_tendency=0.2,
        quit_after_consecutive_fails=10,
        quit_after_minutes=60,
    )

    _PRESETS["tester_bot"] = PlayerProfile(
        persona_id="tester_bot",
        persona_name="Automated Tester (no quit, max endurance)",
        session_duration_min=540,
        sessions_per_day=1,
        retry_on_fail=999,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=False,
        max_ads_per_session=0,
        look_ahead_turns=1,
        tap_precision_px=0,
        decision_speed_sec=0.0,
        booster_save_tendency=0.5,
        quit_after_consecutive_fails=999,
        quit_after_minutes=999,
    )


def load_persona(persona_id: str) -> PlayerProfile:
    """프리셋 ID로 PlayerProfile 로드."""
    if not _PRESETS:
        _register_builtins()

    profile = _PRESETS.get(persona_id)
    if profile is None:
        raise ValueError(
            f"Unknown persona: {persona_id}. "
            f"Available: {list(_PRESETS.keys())}"
        )
    return profile


def list_personas() -> List[str]:
    """등록된 페르소나 목록."""
    if not _PRESETS:
        _register_builtins()
    return list(_PRESETS.keys())
