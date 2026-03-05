"""
Screen State Machine
=====================
Manages screen-level state transitions with:
  - Verified transition tracking (expected vs actual)
  - Stuck detection with escalating strategies
  - Screen classification confidence tracking
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ScreenState:
    """Represents a known screen state."""
    screen_type: str
    entry_count: int = 0
    total_ticks: int = 0
    last_entered: float = 0.0
    successful_exits: Dict[str, int] = field(default_factory=dict)  # target -> count
    failed_exits: Dict[str, int] = field(default_factory=dict)      # target -> count


class ScreenStateMachine:
    """Tracks screen-level state and detects stuck conditions.

    Unlike the old STUCK_THRESHOLD=5 with unconditional reset,
    this verifies actual screen changes before clearing stuck state.
    """

    STUCK_LEVELS = [
        # (threshold_ticks, strategy)
        (5, "bt_alternative"),     # Try different BT branch
        (10, "back_key"),          # Press back
        (15, "navigate_hub"),      # Navigate to lobby/battle
        (20, "discovery"),         # Grid exploration
        (25, "vision"),            # Ask Vision AI
        (30, "relaunch"),          # Restart game
    ]

    def __init__(self):
        self._states: Dict[str, ScreenState] = {}
        self._current: Optional[str] = None
        self._previous: Optional[str] = None
        self._same_screen_ticks: int = 0
        self._last_escape_level: int = -1
        self._screen_history: List[str] = []

    @property
    def current(self) -> Optional[str]:
        return self._current

    @property
    def previous(self) -> Optional[str]:
        return self._previous

    @property
    def same_screen_ticks(self) -> int:
        return self._same_screen_ticks

    def update(self, screen_type: str) -> bool:
        """Update state machine with detected screen.

        Returns True if screen changed.
        """
        self._screen_history.append(screen_type)
        if len(self._screen_history) > 50:
            self._screen_history = self._screen_history[-50:]

        if screen_type == self._current:
            self._same_screen_ticks += 1
            return False

        # Screen changed
        self._previous = self._current
        self._current = screen_type
        self._same_screen_ticks = 0
        self._last_escape_level = -1

        # Update state tracking
        if screen_type not in self._states:
            self._states[screen_type] = ScreenState(screen_type=screen_type)
        state = self._states[screen_type]
        state.entry_count += 1
        state.last_entered = time.time()

        # Record successful exit from previous screen
        if self._previous and self._previous in self._states:
            prev_state = self._states[self._previous]
            prev_state.successful_exits[screen_type] = \
                prev_state.successful_exits.get(screen_type, 0) + 1

        logger.info("SM: %s -> %s (entry #%d)",
                     self._previous or "None", screen_type, state.entry_count)
        return True

    def get_stuck_strategy(self) -> Optional[str]:
        """Check if stuck, returning the appropriate escape strategy.

        Returns None if not stuck. Returns strategy name if stuck.
        Each call returns the NEXT level strategy (escalating).
        """
        for i, (threshold, strategy) in enumerate(self.STUCK_LEVELS):
            if self._same_screen_ticks >= threshold and i > self._last_escape_level:
                self._last_escape_level = i
                logger.info("SM: stuck on '%s' (%d ticks) -> strategy: %s",
                            self._current, self._same_screen_ticks, strategy)
                return strategy
        return None

    def verify_escape(self, new_screen_type: str) -> bool:
        """Verify that an escape attempt actually changed the screen.

        Call this AFTER an escape action + new screenshot/detection.
        Only resets stuck counter if screen actually changed.
        """
        if new_screen_type != self._current:
            self.update(new_screen_type)
            return True
        # Escape failed -- stuck counter keeps ticking
        if self._current and self._current in self._states:
            target = "escape_failed"
            self._states[self._current].failed_exits[target] = \
                self._states[self._current].failed_exits.get(target, 0) + 1
        return False

    def get_oscillation(self) -> Optional[Tuple[str, str]]:
        """Detect A->B->A->B oscillation pattern.

        Returns (screen_a, screen_b) if oscillating, None otherwise.
        """
        h = self._screen_history
        if (len(h) >= 4
                and h[-1] == h[-3]
                and h[-2] == h[-4]
                and h[-1] != h[-2]):
            return (h[-2], h[-1])
        return None

    def get_state_info(self, screen_type: str) -> Optional[ScreenState]:
        return self._states.get(screen_type)

    def get_visit_count(self, screen_type: str) -> int:
        state = self._states.get(screen_type)
        return state.entry_count if state else 0

    def get_history(self, n: int = 10) -> List[str]:
        return self._screen_history[-n:]
