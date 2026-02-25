"""
GameBrain Abstract Base Class
==============================
게임별 AI 두뇌의 공통 인터페이스 정의.
perceive → decide → translate_to_input 사이클.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


# ============================================================
# Data classes
# ============================================================

class ActionType(str, Enum):
    """게임 행동 유형."""
    TAP = "tap"
    SWIPE = "swipe"
    LONG_PRESS = "long_press"
    KEY_PRESS = "key_press"
    WAIT = "wait"


@dataclass
class TouchInput:
    """터치/입력 이벤트 하나를 표현."""
    action_type: ActionType
    x: float = 0.0
    y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    duration: float = 0.0
    key: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GameAction:
    """Brain이 결정한 게임 행동."""
    name: str
    description: str = ""
    confidence: float = 1.0
    inputs: List[TouchInput] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GameState:
    """게임 상태 스냅샷.

    parsed dict may contain:
      - "screen_type": str — classified screen type
      - "confidence": float — classification confidence
      - "is_popup": bool — popup overlay detected
      - "snapshot": GameStateSnapshot — structured state from Layer 1 perception
        (HP/MP gauges, gold/level OCR readings, etc.)
    """
    raw: Any = None
    parsed: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    is_game_over: bool = False
    timestamp: float = 0.0


# ============================================================
# Abstract base class
# ============================================================

class GameBrain(ABC):
    """
    게임별 AI 두뇌 추상 클래스.

    각 게임은 이 클래스를 상속하여:
    1. perceive(): 원시 상태 → 파싱된 상태
    2. decide(): 파싱된 상태 → 행동 결정
    3. translate_to_input(): 행동 → 터치/키 입력
    """

    def __init__(self, skill_level: float = 0.5):
        """
        Args:
            skill_level: 플레이어 숙련도 (0.0~1.0).
                         높을수록 최적 행동 선택 확률 증가.
        """
        self.skill_level = max(0.0, min(1.0, skill_level))

    @abstractmethod
    def perceive(self, raw_state: Any) -> GameState:
        """원시 게임 상태를 파싱하여 GameState로 변환."""
        ...

    @abstractmethod
    def decide(self, state: GameState) -> GameAction:
        """현재 상태에서 다음 행동을 결정."""
        ...

    @abstractmethod
    def translate_to_input(self, action: GameAction) -> List[TouchInput]:
        """행동을 구체적 입력 이벤트로 변환."""
        ...

    def step(self, raw_state: Any) -> GameAction:
        """perceive → decide → translate_to_input 한 사이클 실행."""
        state = self.perceive(raw_state)
        action = self.decide(state)
        action.inputs = self.translate_to_input(action)
        return action
