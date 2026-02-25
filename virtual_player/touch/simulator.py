"""
Touch Simulator
================
TouchInput을 실제 입력으로 변환하기 위한 시뮬레이터.
어댑터에서 사용하는 중간 레이어.
"""

import asyncio
import time
from typing import List, Optional
from ..brain.base import TouchInput, ActionType
from .humanizer import Humanizer


class TouchSimulator:
    """터치 입력 시뮬레이션."""

    def __init__(self, humanizer: Optional[Humanizer] = None):
        self.humanizer = humanizer or Humanizer()
        self._last_input_time: float = 0.0

    async def prepare_inputs(self, inputs: List[TouchInput], fatigue: float = 0.0) -> List[TouchInput]:
        """입력 목록에 인간적 변형을 적용."""
        result = []
        for inp in inputs:
            humanized = self.humanizer.apply(inp, fatigue=fatigue)
            result.append(humanized)
        return result

    def get_delay_before_next(self, fatigue: float = 0.0) -> float:
        """다음 입력까지의 대기 시간 반환."""
        return self.humanizer.get_delay(fatigue=fatigue)
