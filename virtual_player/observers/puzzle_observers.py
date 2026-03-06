"""
Puzzle Observers -- Puzzle Genre-Specific Parameter Observers
==============================================================
Board analysis, match mechanics, holder state for puzzle games.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import ObserverBase, ScreenCaptureFn

logger = logging.getLogger(__name__)


class BoardObserver(ObserverBase):
    """Observes puzzle board: dimensions, colors, stack depth."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        board_scanner: Optional[Callable] = None,
    ):
        """
        Args:
            board_scanner: (screenshot_path) -> {"columns": int, "rows": int,
                            "colors": [str], "cars": [dict], ...}
        """
        super().__init__(5, "BoardAnalyst", "ingame", capture_fn, observations)
        self._scan_board = board_scanner
        self._level_boards: List[Dict] = []

    def record_board_state(self, board_data: Dict) -> None:
        """Record a board state for later analysis."""
        self._level_boards.append(board_data)

    def run(self) -> None:
        if self._scan_board:
            p = self.screenshot("board_scan")
            if p:
                board = self._scan_board(p)
                if board:
                    self._analyze_board(board)
                    return

        if self._level_boards:
            for board in self._level_boards:
                self._analyze_board(board)

    def _analyze_board(self, board: Dict) -> None:
        cols = board.get("columns", 0)
        if cols > 0:
            self.observe("board_width_cells", cols, confidence=0.8,
                         notes="Scanned from board state")

        rows = board.get("rows", 0)
        if rows > 0:
            self.observe("board_height_cells", rows, confidence=0.7,
                         notes="Max stack depth as height")

        colors = board.get("colors", [])
        if colors:
            self.observe("car_color_count", len(set(colors)), confidence=0.8,
                         notes=f"Colors: {sorted(set(colors))}")

        stack_depths = board.get("stack_depths", [])
        if stack_depths:
            self.observe("stack_depth_range",
                         {"min": min(stack_depths), "max": max(stack_depths)},
                         confidence=0.7,
                         notes=f"Depths: {stack_depths}")


class MatchObserver(ObserverBase):
    """Observes match mechanics: threshold, holder capacity."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
    ):
        super().__init__(6, "MatchMechanic", "mechanics", capture_fn, observations)
        self._match_events: List[Dict] = []

    def record_match_event(self, event: Dict) -> None:
        """Record a match event (holder before/after, matched items)."""
        self._match_events.append(event)

    def run(self) -> None:
        if not self._match_events:
            # Default puzzle match threshold
            self.observe("match_threshold", 3, confidence=0.5,
                         notes="Default puzzle genre assumption")
            return

        thresholds = [e.get("matched_count", 3) for e in self._match_events]
        if thresholds:
            most_common = max(set(thresholds), key=thresholds.count)
            self.observe("match_threshold", most_common,
                         confidence=0.9 if len(set(thresholds)) == 1 else 0.7,
                         notes=f"Observed from {len(self._match_events)} match events")

        # Holder capacity from events
        capacities = [e.get("holder_capacity") for e in self._match_events
                      if e.get("holder_capacity")]
        if capacities:
            self.observe("holder_capacity", max(capacities), confidence=0.9,
                         notes="Observed max holder capacity")


class HolderObserver(ObserverBase):
    """Observes holder/hand: capacity, current state."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        holder_scanner: Optional[Callable] = None,
    ):
        """
        Args:
            holder_scanner: (screenshot_path) -> [color_or_None, ...] for each slot.
        """
        super().__init__(7, "HolderAnalyst", "ingame", capture_fn, observations)
        self._scan_holder = holder_scanner

    def run(self) -> None:
        if not self._scan_holder:
            return

        p = self.screenshot("holder_scan")
        if not p:
            return

        holder = self._scan_holder(p)
        if holder:
            capacity = len(holder)
            self.observe("holder_capacity", capacity, confidence=0.95,
                         notes=f"Direct slot count: {capacity}")
            filled = sum(1 for s in holder if s is not None)
            self.observe("holder_fill_ratio", round(filled / capacity, 2),
                         confidence=0.8,
                         notes=f"{filled}/{capacity} slots filled")
