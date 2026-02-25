"""
Plan Adapter — Adaptive Decision Orchestrator
===============================================
Wraps GoalReasoner with three adaptive layers:

1. FailureMemory  — skip actions known to fail on this screen
2. LoopDetector   — detect loops and execute escape strategies
3. SpatialMemory  — track zone info for informed escapes

Call flow:
  PlanAdapter.decide(snapshot)
    → observe_zone (spatial)
    → detect loops
    → escape if loop found
    → GoalReasoner.decide(snapshot)
    → filter known-bad action
    → record tick

Call PlanAdapter.report_outcome() after every executed action.
"""

from typing import Optional

from ..adb import log
from ..reasoning.goap_planner import GOAPAction
from .failure_memory import FailureMemory
from .loop_detector import LoopDetector
from .spatial_memory import SpatialMemory


class PlanAdapter:
    """Wraps GoalReasoner with adaptive failure/loop/spatial filtering."""

    def __init__(
        self,
        reasoner,           # GoalReasoner instance
        failure_memory: FailureMemory,
        loop_detector: LoopDetector,
        spatial_memory: SpatialMemory,
    ) -> None:
        self._reasoner = reasoner
        self._failure = failure_memory
        self._loops = loop_detector
        self._spatial = spatial_memory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(self, snapshot) -> Optional[GOAPAction]:
        """
        Adaptive decision pipeline:
          1. Update spatial memory for the current zone.
          2. Run loop detection and execute escape if needed.
          3. Delegate to GoalReasoner.
          4. Filter out known-bad actions.
          5. Record tick for next iteration.
        """
        screen_type = snapshot.screen_type
        state_hash = LoopDetector.compute_state_hash(snapshot)

        # 1. Update spatial memory
        self._spatial.observe_zone(screen_type, snapshot)

        # 2. Check for loops and try to escape
        loop = self._loops.detect()
        if loop.detected:
            log(
                f"  [PlanAdapter] Loop detected: {loop.loop_type} — {loop.details} "
                f"(escape: {loop.escape_strategy})"
            )
            escape = self._handle_loop(loop, snapshot)
            if escape:
                # Record the escape action as a tick so we don't re-detect immediately
                self._loops.record_tick(
                    screen_type, escape.name,
                    self._reasoner.current_goal, state_hash,
                )
                return escape

        # 3. Check locked goal (informational — GoalReasoner honours it via current_goal)
        locked = self._loops.get_locked_goal()
        if locked:
            log(f"  [PlanAdapter] Goal locked to '{locked}'")

        # 4. Get action from GoalReasoner
        action = self._reasoner.decide(snapshot)

        if action is None:
            return None

        # 5. Pre-filter: skip actions known to fail here
        coords = self._extract_coords(action)
        if coords and self._failure.is_known_failure(screen_type, action.name, coords):
            log(
                f"  [PlanAdapter] Skipping known-bad: {action.name} at {coords} "
                f"on '{screen_type}'"
            )
            # Record the skip as a tick with a sentinel action name so the
            # stagnation detector can fire if every candidate is filtered.
            self._loops.record_tick(
                screen_type, f"_skipped_{action.name}",
                self._reasoner.current_goal, state_hash,
            )
            return None

        # 6. Record tick for loop detection
        self._loops.record_tick(
            screen_type, action.name,
            self._reasoner.current_goal, state_hash,
        )

        return action

    def report_outcome(
        self,
        action_name: str,
        screen_type: str,
        coords: tuple,
        success: bool,
        new_screen: Optional[str] = None,
    ) -> None:
        """Report the outcome of an executed action for learning."""
        if success:
            self._failure.record_success(screen_type, action_name, coords)
        else:
            failure_type = "wrong_screen" if new_screen else "no_transition"
            self._failure.record_failure(
                screen_type, action_name, coords, failure_type
            )
            log(
                f"  [PlanAdapter] Failure recorded: {action_name} on "
                f"'{screen_type}' ({failure_type})"
            )

    @property
    def reasoner(self):
        """Direct access to the underlying GoalReasoner."""
        return self._reasoner

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_loop(self, loop, snapshot) -> Optional[GOAPAction]:
        """Execute the escape strategy for a detected loop."""
        strategy = loop.escape_strategy

        if strategy == "navigate_hub":
            # Find a safe hub zone to break the oscillation
            hub = self._spatial.find_zone_with_resource("hub")
            if not hub:
                safe = self._spatial.get_safe_zones()
                hub = safe[0] if safe else "lobby"
            log(f"  [PlanAdapter] Escape navigate_hub → '{hub}'")
            return GOAPAction(
                name=f"escape_to_{hub}",
                required_screen=hub,
                cost=0.0,
            )

        elif strategy == "alternative_action":
            # Signal the caller to pick a different action; PlanAdapter
            # will return None so the navigation layer can handle it.
            log("  [PlanAdapter] Escape alternative_action — returning None for fallback")
            return None

        elif strategy == "lock_goal":
            # Commit to the current goal for the next 10 ticks
            current = self._reasoner.current_goal
            if current:
                self._loops.lock_goal(current, ticks=10)
                log(f"  [PlanAdapter] Escape lock_goal → '{current}'")
            # Do not interrupt the current action
            return None

        elif strategy == "explore_new":
            # Navigate to an unvisited zone
            # We pass an empty list so only truly unknown zones are chosen;
            # callers that know the full screen list may subclass and override.
            unexplored = self._spatial.get_unexplored_zones([])
            if unexplored:
                target = unexplored[0]
                log(f"  [PlanAdapter] Escape explore_new → '{target}'")
                return GOAPAction(
                    name=f"explore_{target}",
                    required_screen=target,
                    cost=0.0,
                )
            log("  [PlanAdapter] Escape explore_new — no unexplored zones known")
            return None

        return None

    def _extract_coords(self, action: GOAPAction) -> Optional[tuple]:
        """Extract tap coordinates from a GOAPAction's metadata, if present."""
        metadata = getattr(action, "metadata", None) or {}
        raw = metadata.get("coords")
        if raw is not None:
            try:
                return tuple(raw)
            except TypeError:
                pass
        return None
