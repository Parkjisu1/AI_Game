"""
Session Manager
================
세션 수명 주기 관리, 피로도 추적, 휴식 판단.
"""

import random
import time
from dataclasses import dataclass, field
from typing import Optional
from ..config import FATIGUE_RATE_PER_MINUTE, FATIGUE_MAX
from .patterns import SessionPattern, get_session_pattern


@dataclass
class SessionState:
    """현재 세션 상태."""
    session_id: str = ""
    game_id: str = ""
    persona_name: str = ""
    pattern_name: str = ""
    start_time: float = 0.0
    planned_duration_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    fatigue: float = 0.0
    action_count: int = 0
    is_on_break: bool = False
    is_finished: bool = False


class SessionManager:
    """세션 수명 주기 관리."""

    def __init__(self, pattern: SessionPattern):
        self.pattern = pattern
        self.state = SessionState()
        self._break_end_time: float = 0.0

    def start(self, session_id: str, game_id: str, persona_name: str) -> SessionState:
        """세션 시작."""
        duration_min, duration_max = self.pattern.duration_minutes
        planned_minutes = random.uniform(duration_min, duration_max)

        self.state = SessionState(
            session_id=session_id,
            game_id=game_id,
            persona_name=persona_name,
            pattern_name=self.pattern.name,
            start_time=time.time(),
            planned_duration_seconds=planned_minutes * 60,
        )
        return self.state

    def update(self) -> SessionState:
        """세션 상태 업데이트 (매 틱 호출)."""
        if self.state.is_finished:
            return self.state

        now = time.time()
        self.state.elapsed_seconds = now - self.state.start_time

        # Update fatigue
        elapsed_minutes = self.state.elapsed_seconds / 60.0
        self.state.fatigue = min(
            FATIGUE_MAX,
            elapsed_minutes * FATIGUE_RATE_PER_MINUTE,
        )

        # Check if session should end
        if self.state.elapsed_seconds >= self.state.planned_duration_seconds:
            self.state.is_finished = True
            return self.state

        # Check if on break
        if self.state.is_on_break:
            if now >= self._break_end_time:
                self.state.is_on_break = False
            return self.state

        return self.state

    def record_action(self) -> None:
        """행동 1회 기록."""
        self.state.action_count += 1

    def maybe_take_break(self) -> bool:
        """휴식 필요 여부 판단 + 자동 진입."""
        if self.state.is_on_break or self.state.is_finished:
            return False

        if random.random() < self.pattern.break_probability * 0.01:
            # Scale probability per action, not per session
            break_min, break_max = self.pattern.break_duration_seconds
            break_duration = random.uniform(break_min, break_max)
            self.state.is_on_break = True
            self._break_end_time = time.time() + break_duration
            return True
        return False

    def finish(self) -> SessionState:
        """세션 종료."""
        self.state.is_finished = True
        self.state.elapsed_seconds = time.time() - self.state.start_time
        return self.state
