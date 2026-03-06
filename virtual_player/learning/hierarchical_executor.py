"""
HierarchicalPatternExecutor -- Sub-Pattern Support and Flexible Screen Matching
===============================================================================
Extends PatternExecutor to handle multi-level UI flows (e.g., equip->enhance->material->confirm).

Key improvements over PatternExecutor:
- screen_type_alternatives: accept multiple screen types per step
- max_wait_s: poll until expected_screen appears before timing out
- sub_pattern: push current position onto stack, execute sub-pattern, pop back
- on_fail_pattern: run recovery pattern on step failure, then retry
- Built-in recovery patterns: "close_popup", "back_to_hub"
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .action_pattern import ActionStep, ActionPattern, PatternDB
from .pattern_executor import PatternExecutor

logger = logging.getLogger(__name__)

# Built-in recovery pattern names
_BUILTIN_CLOSE_POPUP = "close_popup"
_BUILTIN_BACK_TO_HUB = "back_to_hub"


class HierarchicalPatternExecutor(PatternExecutor):
    """PatternExecutor with call-stack sub-pattern support and flexible screen matching.

    Integrates into PlayEngine as a drop-in replacement for PatternExecutor.
    """

    MAX_STACK_DEPTH = 8  # prevent infinite recursion

    def __init__(
        self,
        pattern_db: PatternDB,
        tap_fn: Callable[[int, int, float], None],
        read_text_fn: Callable[[Any], List[Tuple[str, float, int, int]]],
        detect_screen_fn: Optional[Callable] = None,
        nav_graph: Any = None,
        swipe_fn: Optional[Callable] = None,
        back_fn: Optional[Callable[[], None]] = None,
        navigate_to_fn: Optional[Callable[[str], bool]] = None,
        screenshot_fn: Optional[Callable[[str], Any]] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        """
        Args:
            pattern_db: PatternDB with learned patterns.
            tap_fn: (x, y, wait) -> None. ADB tap.
            read_text_fn: (screenshot_path) -> [(text, conf, y, x)].
            detect_screen_fn: (screenshot_path) -> screen_type string.
            nav_graph: Optional nav graph for element matching.
            swipe_fn: Optional swipe callback.
            back_fn: Optional Android back key callback (for "close_popup" recovery).
            navigate_to_fn: Optional navigator callback (for "back_to_hub" recovery).
            screenshot_fn: Optional screenshot callback for polling.
            screen_width: Device screen width.
            screen_height: Device screen height.
        """
        super().__init__(
            pattern_db=pattern_db,
            tap_fn=tap_fn,
            read_text_fn=read_text_fn,
            detect_screen_fn=detect_screen_fn,
            nav_graph=nav_graph,
            swipe_fn=swipe_fn,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        self._back_fn = back_fn
        self._navigate_to_fn = navigate_to_fn
        self._screenshot_fn = screenshot_fn

        # Call stack: list of (pattern_name, step_idx) for sub-pattern support
        self._stack: List[Tuple[str, int]] = []

    # ------------------------------------------------------------------
    # Public interface (overrides)
    # ------------------------------------------------------------------

    def execute_step(
        self,
        screen_type: str,
        screenshot_path: Any = None,
    ) -> Optional[str]:
        """Execute the next step of the active pattern with hierarchical support.

        Overrides PatternExecutor.execute_step():
        - Accepts screen_type_alternatives in addition to step.screen_type
        - Polls for expected_screen up to step.max_wait_s
        - Handles sub_pattern push/pop
        - Runs on_fail_pattern recovery on screen mismatch exhaustion
        """
        if not self._active_pattern:
            return None

        if self._active_step_idx >= len(self._active_pattern.steps):
            # Current pattern complete -- pop stack if any
            if self._stack:
                self._pop_pattern()
                return f"sub_pattern:complete:returning_to_stack"
            self._complete_pattern(success=True)
            return None

        step = self._active_pattern.steps[self._active_step_idx]

        # --- Screen matching (flexible) ---
        if not self._screen_matches(step, screen_type):
            self._retry_count += 1
            logger.debug(
                "HierarchicalExec: screen mismatch -- got '%s', expected '%s' or %s (retry %d/%d)",
                screen_type, step.screen_type, step.screen_type_alternatives,
                self._retry_count, self.MAX_RETRIES,
            )
            if self._retry_count > self.MAX_RETRIES:
                # Try on_fail_pattern recovery
                if step.on_fail_pattern:
                    recovered = self._run_recovery(step.on_fail_pattern, screen_type)
                    if recovered:
                        self._retry_count = 0
                        return f"recovery:{step.on_fail_pattern}"
                logger.warning(
                    "HierarchicalExec: aborting pattern '%s' -- stuck on '%s' (expected '%s')",
                    self._active_pattern.name, screen_type, step.screen_type,
                )
                self._complete_pattern(success=False)
            return None

        # Reset retry counter on screen match
        self._retry_count = 0

        # --- Sub-pattern: push current position, start sub-pattern ---
        if step.sub_pattern:
            sub_available = self._db.get(step.sub_pattern) is not None
            # Check built-in patterns too
            if not sub_available:
                sub_available = step.sub_pattern in (_BUILTIN_CLOSE_POPUP, _BUILTIN_BACK_TO_HUB)

            if sub_available and len(self._stack) < self.MAX_STACK_DEPTH:
                print(f"[HierarchicalExec] Sub-pattern push: '{step.sub_pattern}' "
                      f"(from '{self._active_pattern.name}' step {self._active_step_idx})")
                # Advance step index before pushing so we resume at next step
                self._active_step_idx += 1
                self._push_pattern(step.sub_pattern)
                return f"sub_pattern:push:{step.sub_pattern}"

        # --- Execute the step ---
        action_desc = self._execute_single_step(step, screenshot_path)

        if action_desc:
            self._active_step_idx += 1
            self._last_attempt_time = time.time()

            remaining = len(self._active_pattern.steps) - self._active_step_idx
            print(f"[HierarchicalExec] Step {self._active_step_idx}/{len(self._active_pattern.steps)}: "
                  f"{action_desc} ({remaining} remaining)")

            # --- Poll for expected screen transition ---
            if step.expected_screen and step.max_wait_s > 0:
                self._wait_for_screen(step.expected_screen, step.max_wait_s)

            # Check if pattern is complete
            if self._active_step_idx >= len(self._active_pattern.steps):
                if self._stack:
                    self._pop_pattern()
                    return f"{action_desc} | sub_complete"
                self._complete_pattern(success=True)

        return action_desc

    # ------------------------------------------------------------------
    # Stack management
    # ------------------------------------------------------------------

    def _push_pattern(self, pattern_name: str) -> bool:
        """Save current position and start a new (sub-)pattern.

        The caller must have already incremented _active_step_idx to
        the step AFTER the sub_pattern trigger step.
        """
        if not self._active_pattern:
            return False

        # Save current position
        self._stack.append((self._active_pattern.name, self._active_step_idx))

        # Handle built-in patterns
        if pattern_name == _BUILTIN_CLOSE_POPUP:
            self._execute_builtin_close_popup()
            # Immediately pop back -- built-ins are synchronous
            self._pop_pattern()
            return True
        if pattern_name == _BUILTIN_BACK_TO_HUB:
            self._execute_builtin_back_to_hub()
            self._pop_pattern()
            return True

        # Start the sub-pattern from DB
        return self.start_pattern(pattern_name)

    def _pop_pattern(self) -> bool:
        """Restore the previous pattern position after sub-pattern completes."""
        if not self._stack:
            return False

        parent_name, parent_step = self._stack.pop()
        parent_pattern = self._db.get(parent_name)
        if parent_pattern is None:
            logger.warning("HierarchicalExec: parent pattern '%s' not in DB after pop", parent_name)
            self._active_pattern = None
            self._active_step_idx = 0
            return False

        self._active_pattern = parent_pattern
        self._active_step_idx = parent_step
        self._retry_count = 0

        print(f"[HierarchicalExec] Sub-pattern complete -- resuming '{parent_name}' "
              f"at step {parent_step}/{len(parent_pattern.steps)}")
        logger.info(
            "HierarchicalExec: popped stack, resuming '%s' at step %d",
            parent_name, parent_step,
        )
        return True

    # ------------------------------------------------------------------
    # Screen matching helpers
    # ------------------------------------------------------------------

    def _screen_matches(self, step: ActionStep, screen_type: str) -> bool:
        """Return True if screen_type is acceptable for this step."""
        # No constraint -> always matches
        if not step.screen_type:
            return True
        # Primary match
        if step.screen_type == screen_type:
            return True
        # Special "unknown" -> always matches
        if step.screen_type == "unknown":
            return True
        # Alternatives
        if screen_type in step.screen_type_alternatives:
            return True
        return False

    def _wait_for_screen(self, expected: str, max_wait: float) -> bool:
        """Poll until detect_screen returns expected or timeout.

        Returns True if expected screen reached within timeout.
        """
        if not self._detect_screen or not self._screenshot_fn:
            time.sleep(min(max_wait, 2.0))
            return False

        deadline = time.time() + max_wait
        poll_interval = 0.5
        while time.time() < deadline:
            time.sleep(poll_interval)
            try:
                path = self._screenshot_fn("hpe_poll")
                if path:
                    current = self._detect_screen(path)
                    if current == expected:
                        logger.debug(
                            "HierarchicalExec: reached expected screen '%s'", expected)
                        return True
            except Exception as e:
                logger.debug("HierarchicalExec: poll error: %s", e)

        logger.debug(
            "HierarchicalExec: timed out waiting for screen '%s' (%.1fs)", expected, max_wait)
        return False

    # ------------------------------------------------------------------
    # Recovery helpers
    # ------------------------------------------------------------------

    def _run_recovery(self, recovery_name: str, current_screen: str) -> bool:
        """Execute a recovery pattern synchronously, return True if handled."""
        print(f"[HierarchicalExec] Running recovery: '{recovery_name}' (current='{current_screen}')")
        logger.info("HierarchicalExec: recovery '%s' on screen '%s'", recovery_name, current_screen)

        if recovery_name == _BUILTIN_CLOSE_POPUP:
            return self._execute_builtin_close_popup()
        if recovery_name == _BUILTIN_BACK_TO_HUB:
            return self._execute_builtin_back_to_hub()

        # DB pattern recovery -- run synchronously (up to MAX_RETRIES steps)
        pattern = self._db.get(recovery_name)
        if not pattern:
            return False
        for step in pattern.steps:
            self._execute_single_step(step, None)
        return True

    def _execute_builtin_close_popup(self) -> bool:
        """Press Android back key to close popup/overlay."""
        if self._back_fn:
            print("[HierarchicalExec] Built-in: close_popup (back key)")
            self._back_fn()
            time.sleep(0.8)
            return True
        # Fallback: tap top-right X area
        self._tap(978, 165, 0.8)
        return True

    def _execute_builtin_back_to_hub(self) -> bool:
        """Navigate to lobby/hub screen."""
        if self._navigate_to_fn:
            print("[HierarchicalExec] Built-in: back_to_hub")
            for hub in ("lobby", "town", "main"):
                try:
                    if self._navigate_to_fn(hub):
                        return True
                except Exception:
                    continue
        # Fallback: press back several times
        if self._back_fn:
            for _ in range(3):
                self._back_fn()
                time.sleep(0.5)
            return True
        return False
