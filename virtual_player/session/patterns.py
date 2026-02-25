"""
Session Patterns
=================
플레이 세션 패턴 정의 (commuter, evening, binge).
"""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class SessionPattern:
    """세션 패턴."""
    name: str
    description: str
    duration_minutes: Tuple[int, int]  # (min, max)
    break_probability: float   # 0.0~1.0 (chance of taking a break mid-session)
    break_duration_seconds: Tuple[int, int]  # (min, max) if break happens
    time_of_day: Tuple[int, int]  # (start_hour, end_hour) 24h format


# ============================================================
# Preset patterns
# ============================================================

SESSION_PATTERNS: Dict[str, SessionPattern] = {
    "commuter": SessionPattern(
        name="commuter",
        description="출퇴근 짧은 세션",
        duration_minutes=(10, 20),
        break_probability=0.1,
        break_duration_seconds=(5, 15),
        time_of_day=(7, 9),
    ),
    "evening": SessionPattern(
        name="evening",
        description="저녁 여유 세션",
        duration_minutes=(30, 60),
        break_probability=0.3,
        break_duration_seconds=(10, 60),
        time_of_day=(19, 23),
    ),
    "binge": SessionPattern(
        name="binge",
        description="장시간 몰입 세션",
        duration_minutes=(90, 150),
        break_probability=0.5,
        break_duration_seconds=(30, 120),
        time_of_day=(20, 2),  # can cross midnight
    ),
}


def get_session_pattern(name: str) -> SessionPattern:
    """이름으로 세션 패턴 가져오기."""
    if name not in SESSION_PATTERNS:
        available = ", ".join(SESSION_PATTERNS.keys())
        raise ValueError(f"Unknown session pattern '{name}'. Available: {available}")
    return SESSION_PATTERNS[name]
