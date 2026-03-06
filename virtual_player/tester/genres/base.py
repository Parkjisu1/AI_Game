"""
GenreProfile — 장르별 공통 규칙 기본 클래스
=============================================
장르 수준에서 공유되는 행동 패턴, UI 패턴, 인식 힌트를 정의.

게임 고유 규칙은 여기에 넣지 않는다 → Playbook 담당.
플레이어 성향도 여기에 넣지 않는다 → PlayerProfile 담당.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ActionCategory:
    """행동 범주별 비중 (장르 특성 정의)."""
    navigate: float = 0.0    # 화면 간 이동
    select: float = 0.0      # 오브젝트 선택/탭
    place: float = 0.0       # 드래그&드롭, 배치
    activate: float = 0.0    # 스킬/부스터 사용
    wait: float = 0.0        # 의도적 대기
    decide: float = 0.0      # 리소스 분배 판단
    respond: float = 0.0     # 팝업/광고 반응


@dataclass
class GenreProfile:
    """장르 수준 공통 규칙.

    한 장르에 속하는 모든 게임이 공유하는 패턴.
    예: 모든 퍼즐 게임은 "lobby→gameplay→win/fail→lobby" 흐름을 가진다.
    """

    genre_id: str                    # puzzle_match, idle_rpg, merge, ...
    genre_name: str                  # "Puzzle Match", "Idle RPG", ...

    # 행동 비중 (장르 특성)
    action_mix: ActionCategory = field(default_factory=ActionCategory)

    # 장르 공통 화면 흐름
    # "lobby" → ["gameplay"], "gameplay" → ["win", "fail"], ...
    screen_flow: Dict[str, List[str]] = field(default_factory=dict)

    # 장르 공통 UI 패턴 (대부분의 게임에서 통하는 것)
    common_ui_patterns: Dict[str, str] = field(default_factory=lambda: {
        "close_popup": "tap top-right X or back button",
        "close_ad": "tap X corners or back button",
        "navigate_home": "tap bottom home/lobby tab",
    })

    # Perception 프롬프트에 추가할 장르 힌트
    perception_hints: str = ""

    # 장르 공통 금지 행동
    never_do: List[str] = field(default_factory=list)

    # 장르 공통 항상 행동
    always_do: List[str] = field(default_factory=list)

    # 실시간 여부 (False = 턴제/비실시간)
    is_realtime: bool = False

    # 입력 유형
    input_types: List[str] = field(default_factory=lambda: ["tap"])
    # tap, drag, swipe, long_press, pinch

    # 세션 패턴
    typical_session_minutes: int = 10
    typical_level_seconds: int = 60
