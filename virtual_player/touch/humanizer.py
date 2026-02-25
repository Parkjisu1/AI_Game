"""
Humanizer
==========
터치 입력에 인간적 특성(딜레이, 떨림, 좌표 오차)을 추가.
피로도에 따라 오차 증가.
"""

import random
import copy
from ..brain.base import TouchInput, ActionType
from ..config import (
    BASE_ACTION_DELAY,
    JITTER_RANGE,
    TOUCH_OFFSET_RANGE,
    FATIGUE_ERROR_THRESHOLD,
)


class Humanizer:
    """인간적 입력 변형기."""

    def __init__(
        self,
        base_delay: float = BASE_ACTION_DELAY,
        jitter_range: tuple = JITTER_RANGE,
        offset_range: tuple = TOUCH_OFFSET_RANGE,
    ):
        self.base_delay = base_delay
        self.jitter_range = jitter_range
        self.offset_range = offset_range

    def apply(self, touch: TouchInput, fatigue: float = 0.0) -> TouchInput:
        """TouchInput에 인간적 변형 적용. 원본은 변경하지 않음."""
        result = copy.deepcopy(touch)

        # Key press and wait don't need coordinate modification
        if result.action_type in (ActionType.KEY_PRESS, ActionType.WAIT):
            return result

        # Coordinate offset (fatigue increases error)
        fatigue_multiplier = 1.0 + (fatigue * 2.0 if fatigue > FATIGUE_ERROR_THRESHOLD else fatigue * 0.5)
        offset_min, offset_max = self.offset_range
        scaled_range = (offset_min * fatigue_multiplier, offset_max * fatigue_multiplier)

        result.x += random.uniform(*scaled_range)
        result.y += random.uniform(*scaled_range)

        if result.action_type == ActionType.SWIPE:
            result.end_x += random.uniform(*scaled_range)
            result.end_y += random.uniform(*scaled_range)

        # Duration jitter for long press
        if result.action_type == ActionType.LONG_PRESS and result.duration > 0:
            jitter = random.uniform(-0.05, 0.1) * fatigue_multiplier
            result.duration = max(0.1, result.duration + jitter)

        return result

    def get_delay(self, fatigue: float = 0.0) -> float:
        """다음 액션까지의 딜레이 계산."""
        jitter = random.uniform(*self.jitter_range)
        # Fatigue slows down reaction
        fatigue_penalty = fatigue * 0.5
        return self.base_delay + jitter + fatigue_penalty
