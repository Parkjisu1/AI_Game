"""
Loop Detector — 4 Loop Pattern Detection
==========================================
Detects 4 types of loops that indicate the agent is stuck:

1. Screen oscillation  — A→B→A→B or A→B→C→A→B→C
2. Action repetition   — Same action 5x with no state change
3. Goal cycling        — Switching between 2+ goals without progress
4. State stagnation    — Same state hash for 8+ ticks

Each detection returns an escape_strategy hint:
  "navigate_hub"       — Go to a safe central zone
  "alternative_action" — Try a different action on this screen
  "lock_goal"          — Commit to one goal for N ticks
  "explore_new"        — Visit an unvisited zone
"""

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..adb import log


class LoopType(str, Enum):
    OSCILLATION = "oscillation"
    REPETITION = "repetition"
    GOAL_CYCLE = "goal_cycle"
    STAGNATION = "stagnation"


@dataclass
class LoopDetection:
    detected: bool
    loop_type: Optional[LoopType] = None
    details: str = ""
    escape_strategy: str = ""


class LoopDetector:
    OSCILLATION_WINDOW = 8       # screen history length to inspect
    REPETITION_THRESHOLD = 5     # same action N consecutive times
    GOAL_CYCLE_WINDOW = 10       # goal history length to inspect
    STAGNATION_THRESHOLD = 8     # same state hash N ticks

    def __init__(self) -> None:
        self._screen_history: List[str] = []
        self._action_history: List[str] = []
        self._goal_history: List[str] = []
        self._state_hashes: List[str] = []
        self._locked_goal: Optional[str] = None
        self._lock_remaining: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_tick(
        self,
        screen_type: str,
        action_name: str,
        goal_name: Optional[str],
        state_hash: str,
    ) -> None:
        """Record one tick of activity and trim histories."""
        self._screen_history.append(screen_type)
        self._action_history.append(action_name)
        if goal_name:
            self._goal_history.append(goal_name)
        self._state_hashes.append(state_hash)

        max_len = (
            max(
                self.OSCILLATION_WINDOW,
                self.GOAL_CYCLE_WINDOW,
                self.STAGNATION_THRESHOLD,
            )
            + 2
        )
        for hist in [
            self._screen_history,
            self._action_history,
            self._goal_history,
            self._state_hashes,
        ]:
            if len(hist) > max_len:
                del hist[:-max_len]

        # Decrease goal lock counter
        if self._lock_remaining > 0:
            self._lock_remaining -= 1
            if self._lock_remaining == 0:
                log(f"  [LoopDetector] Goal lock on '{self._locked_goal}' expired")
                self._locked_goal = None

    def detect(self) -> LoopDetection:
        """Check for all loop patterns. Returns first one detected."""
        osc = self._check_oscillation()
        if osc:
            log(f"  [LoopDetector] Oscillation: {osc.details}")
            return osc

        rep = self._check_repetition()
        if rep:
            log(f"  [LoopDetector] Repetition: {rep.details}")
            return rep

        cyc = self._check_goal_cycle()
        if cyc:
            log(f"  [LoopDetector] Goal cycle: {cyc.details}")
            return cyc

        stag = self._check_stagnation()
        if stag:
            log(f"  [LoopDetector] Stagnation: {stag.details}")
            return stag

        return LoopDetection(detected=False)

    def get_locked_goal(self) -> Optional[str]:
        """Return the currently locked goal name, or None."""
        return self._locked_goal

    def lock_goal(self, goal_name: str, ticks: int = 10) -> None:
        """Force the agent to pursue a single goal for N ticks."""
        self._locked_goal = goal_name
        self._lock_remaining = ticks
        log(f"  [LoopDetector] Locked goal '{goal_name}' for {ticks} ticks")

    def clear(self) -> None:
        """Reset all histories (e.g., after a scene change)."""
        self._screen_history.clear()
        self._action_history.clear()
        self._goal_history.clear()
        self._state_hashes.clear()

    @staticmethod
    def compute_state_hash(snapshot) -> str:
        """Compute a short hash of relevant game state for stagnation detection."""
        level = getattr(snapshot, "level", 0) or 0
        data = (
            f"{snapshot.screen_type}:"
            f"{snapshot.hp_pct:.2f}:"
            f"{snapshot.gold:.0f}:"
            f"{level}"
        )
        return hashlib.md5(data.encode()).hexdigest()[:8]

    # ------------------------------------------------------------------
    # Pattern checks
    # ------------------------------------------------------------------

    def _check_oscillation(self) -> Optional[LoopDetection]:
        h = self._screen_history

        # Period-2 oscillation: A→B→A→B
        if (
            len(h) >= 4
            and h[-1] == h[-3]
            and h[-2] == h[-4]
            and h[-1] != h[-2]
        ):
            return LoopDetection(
                detected=True,
                loop_type=LoopType.OSCILLATION,
                details=f"{h[-2]}\u2194{h[-1]}",
                escape_strategy="navigate_hub",
            )

        # Period-3 oscillation: A→B→C→A→B→C (must have at least 2 distinct screens)
        if (
            len(h) >= 6
            and h[-1] == h[-4]
            and h[-2] == h[-5]
            and h[-3] == h[-6]
            and len({h[-1], h[-2], h[-3]}) >= 2
        ):
            return LoopDetection(
                detected=True,
                loop_type=LoopType.OSCILLATION,
                details=f"{h[-3]}\u2192{h[-2]}\u2192{h[-1]} cycle",
                escape_strategy="navigate_hub",
            )

        return None

    def _check_repetition(self) -> Optional[LoopDetection]:
        if len(self._action_history) < self.REPETITION_THRESHOLD:
            return None
        recent = self._action_history[-self.REPETITION_THRESHOLD:]
        if len(set(recent)) == 1:
            return LoopDetection(
                detected=True,
                loop_type=LoopType.REPETITION,
                details=f"{recent[0]} x{self.REPETITION_THRESHOLD}",
                escape_strategy="alternative_action",
            )
        return None

    def _check_goal_cycle(self) -> Optional[LoopDetection]:
        if len(self._goal_history) < self.GOAL_CYCLE_WINDOW:
            return None
        recent = self._goal_history[-self.GOAL_CYCLE_WINDOW:]
        unique = set(recent)
        if len(unique) == 2:
            goals = list(unique)
            return LoopDetection(
                detected=True,
                loop_type=LoopType.GOAL_CYCLE,
                details=f"{goals[0]}\u2194{goals[1]}",
                escape_strategy="lock_goal",
            )
        return None

    def _check_stagnation(self) -> Optional[LoopDetection]:
        if len(self._state_hashes) < self.STAGNATION_THRESHOLD:
            return None
        recent = self._state_hashes[-self.STAGNATION_THRESHOLD:]
        if len(set(recent)) == 1:
            return LoopDetection(
                detected=True,
                loop_type=LoopType.STAGNATION,
                details=f"No state change for {self.STAGNATION_THRESHOLD} ticks",
                escape_strategy="explore_new",
            )
        return None
