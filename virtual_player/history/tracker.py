"""
Tracker
========
실시간 행동 기록 (HistoryStorage에 위임).
"""

import time
from typing import Any, Dict, Optional
from ..brain.base import GameAction, GameState
from .storage import HistoryStorage


class Tracker:
    """실시간 행동 기록기."""

    def __init__(self, storage: HistoryStorage):
        self.storage = storage
        self._current_session_id: Optional[str] = None
        self._last_score: float = 0.0

    def begin_session(self, session_id: str, game_id: str,
                      persona_name: str, pattern_name: str,
                      metadata: Optional[Dict] = None) -> None:
        self._current_session_id = session_id
        self._last_score = 0.0
        self.storage.insert_session(
            session_id=session_id,
            game_id=game_id,
            persona_name=persona_name,
            pattern_name=pattern_name,
            start_time=time.time(),
            metadata=metadata,
        )

    def record_action(self, action: GameAction, state: GameState) -> None:
        if not self._current_session_id:
            return

        self._last_score = state.score

        # Build state summary (compact)
        state_summary = ""
        if state.parsed:
            # Just keep keys list for summary
            state_summary = str(list(state.parsed.keys()))

        action_id = self.storage.insert_action(
            session_id=self._current_session_id,
            timestamp=time.time(),
            action_name=action.name,
            action_description=action.description,
            confidence=action.confidence,
            game_score=state.score,
            game_state_summary=state_summary,
            metadata=action.metadata,
        )

        # Record touch events
        for touch in action.inputs:
            self.storage.insert_touch_event(
                action_id=action_id,
                action_type=touch.action_type.value,
                x=touch.x,
                y=touch.y,
                end_x=touch.end_x,
                end_y=touch.end_y,
                duration=touch.duration,
                key_name=touch.key,
                metadata=touch.metadata,
            )

    def end_session(self, duration_seconds: float, action_count: int) -> None:
        if not self._current_session_id:
            return
        self.storage.update_session(
            session_id=self._current_session_id,
            end_time=time.time(),
            duration_seconds=duration_seconds,
            action_count=action_count,
            final_score=self._last_score,
        )
        self._current_session_id = None
