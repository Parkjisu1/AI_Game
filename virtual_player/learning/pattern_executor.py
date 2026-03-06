"""
Pattern Executor -- Adaptive Replay of Learned Patterns
========================================================
Matches current game context to learned patterns and executes them.

Key design: Intent-based matching, NOT coordinate-based.
1. Match by OCR text (find button/item by text on screen)
2. Match by nav_graph element (find element by type)
3. Match by screen region (top/center/bottom)
4. Fallback to stored coordinates (last resort)

Self-learning: records successful/failed executions to improve pattern matching.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .action_pattern import ActionStep, ActionPattern, PatternDB

logger = logging.getLogger(__name__)


class PatternExecutor:
    """Executes learned patterns during autonomous play.

    Integrates into PlayEngine's decision cascade as a new level
    between GOAP and ScreenActionResolver.
    """

    OCR_MATCH_THRESHOLD = 0.6  # minimum text similarity for matching

    def __init__(
        self,
        pattern_db: PatternDB,
        tap_fn: Callable[[int, int, float], None],
        read_text_fn: Callable[[Any], List[Tuple[str, float, int, int]]],
        detect_screen_fn: Optional[Callable] = None,
        nav_graph: Any = None,
        swipe_fn: Optional[Callable] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        self._db = pattern_db
        self._tap = tap_fn
        self._read_text = read_text_fn
        self._detect_screen = detect_screen_fn
        self._graph = nav_graph
        self._swipe = swipe_fn
        self._screen_w = screen_width
        self._screen_h = screen_height

        # Execution state
        self._active_pattern: Optional[ActionPattern] = None
        self._active_step_idx: int = 0
        self._last_attempt_time: float = 0
        self._retry_count: int = 0
        self.MAX_RETRIES = 3

    @property
    def is_executing(self) -> bool:
        return self._active_pattern is not None

    @property
    def active_pattern_name(self) -> str:
        if self._active_pattern:
            return self._active_pattern.name
        return ""

    def try_match(
        self,
        screen_type: str,
        screenshot_path: Any = None,
        ocr_texts: List[str] = None,
    ) -> Optional[str]:
        """Check if current context matches any learned pattern.

        Returns pattern name if matched, None otherwise.
        Does NOT start execution -- call execute_step() for that.
        """
        if self._active_pattern:
            return self._active_pattern.name

        matches = self._db.get_by_trigger(screen_type, ocr_texts)
        if matches:
            return matches[0].name
        return None

    def start_pattern(self, pattern_name: str) -> bool:
        """Begin executing a named pattern."""
        pattern = self._db.get(pattern_name)
        if not pattern or not pattern.steps:
            return False

        self._active_pattern = pattern
        self._active_step_idx = 0
        self._retry_count = 0
        pattern.use_count += 1
        pattern.last_used = time.strftime("%Y-%m-%dT%H:%M:%S")

        logger.info("PatternExecutor: starting '%s' (%d steps)",
                     pattern.name, len(pattern.steps))
        print(f"[PatternExec] Starting pattern: {pattern.name} ({len(pattern.steps)} steps)")
        return True

    def execute_step(
        self,
        screen_type: str,
        screenshot_path: Any = None,
    ) -> Optional[str]:
        """Execute the next step of the active pattern.

        Returns action description if executed, None if pattern is done/failed.
        """
        if not self._active_pattern:
            return None

        if self._active_step_idx >= len(self._active_pattern.steps):
            self._complete_pattern(success=True)
            return None

        step = self._active_pattern.steps[self._active_step_idx]

        # Verify we're on the expected screen
        if step.screen_type and step.screen_type != screen_type:
            if step.screen_type != "unknown":
                self._retry_count += 1
                if self._retry_count > self.MAX_RETRIES:
                    logger.warning("PatternExecutor: wrong screen '%s' (expected '%s'), aborting",
                                   screen_type, step.screen_type)
                    self._complete_pattern(success=False)
                    return None
                logger.debug("PatternExecutor: wrong screen '%s' (expected '%s'), retrying",
                             screen_type, step.screen_type)
                return None

        # Execute the step
        self._retry_count = 0
        action_desc = self._execute_single_step(step, screenshot_path)

        if action_desc:
            self._active_step_idx += 1
            self._last_attempt_time = time.time()

            remaining = len(self._active_pattern.steps) - self._active_step_idx
            print(f"[PatternExec] Step {self._active_step_idx}/{len(self._active_pattern.steps)}: "
                  f"{action_desc} ({remaining} remaining)")

            # Check if pattern is complete
            if self._active_step_idx >= len(self._active_pattern.steps):
                self._complete_pattern(success=True)

        return action_desc

    def cancel(self):
        """Cancel the active pattern."""
        if self._active_pattern:
            logger.info("PatternExecutor: cancelled '%s'", self._active_pattern.name)
            self._active_pattern = None
            self._active_step_idx = 0

    def _execute_single_step(self, step: ActionStep, screenshot_path: Any = None) -> Optional[str]:
        """Execute a single ActionStep using intent-based matching.

        Priority:
        1. OCR text match (find target text on current screen)
        2. Nav graph element match
        3. Region-based tap
        4. Fallback coordinates
        """
        x, y = step.fallback_x, step.fallback_y
        match_method = "fallback"

        # Method 1: OCR text match -- find the target text on screen
        if step.target_text and screenshot_path:
            ocr_result = self._find_by_text(step.target_text, screenshot_path)
            if ocr_result:
                x, y = ocr_result
                match_method = f"ocr:'{step.target_text[:20]}'"

        # Method 2: Nav graph element match
        elif step.target_element and self._graph:
            elem_result = self._find_by_element(step.target_element, step.screen_type)
            if elem_result:
                x, y = elem_result
                match_method = f"element:{step.target_element}"

        # Method 3: Intent-based OCR search (search for intent keywords)
        elif step.intent and screenshot_path:
            intent_result = self._find_by_intent(step.intent, screenshot_path)
            if intent_result:
                x, y = intent_result
                match_method = f"intent:{step.intent}"

        # Execute the action
        if step.action_type == "tap":
            self._tap(x, y, step.wait_after)
        elif step.action_type in ("swipe", "scroll_down", "scroll_up") and self._swipe:
            dx, dy = 0, 0
            if step.swipe_direction == "up" or step.action_type == "scroll_up":
                dy = -400
            elif step.swipe_direction == "down" or step.action_type == "scroll_down":
                dy = 400
            elif step.swipe_direction == "left":
                dx = -300
            elif step.swipe_direction == "right":
                dx = 300
            self._swipe(x, y, x + dx, y + dy, step.wait_after)
        else:
            self._tap(x, y, step.wait_after)

        return f"{step.intent}:{step.target_desc} [{match_method}] @({x},{y})"

    def _find_by_text(self, target_text: str, screenshot_path: Any) -> Optional[Tuple[int, int]]:
        """Find target text on screen via OCR and return its position."""
        try:
            texts = self._read_text(screenshot_path)
            target_lower = target_text.lower()

            best_match = None
            best_score = 0

            for text_str, conf, ty, tx in texts:
                if not isinstance(text_str, str):
                    continue
                text_lower = text_str.lower()

                # Exact substring match
                if target_lower in text_lower or text_lower in target_lower:
                    score = conf * (len(target_lower) / max(len(text_lower), 1))
                    if score > best_score:
                        best_score = score
                        best_match = (tx, ty)

                # Partial word match
                target_words = set(target_lower.split())
                text_words = set(text_lower.split())
                if target_words and text_words:
                    overlap = len(target_words & text_words) / len(target_words)
                    if overlap > self.OCR_MATCH_THRESHOLD and overlap * conf > best_score:
                        best_score = overlap * conf
                        best_match = (tx, ty)

            return best_match
        except Exception as e:
            logger.debug("PatternExecutor OCR search failed: %s", e)
            return None

    def _find_by_element(self, element_name: str, screen_type: str) -> Optional[Tuple[int, int]]:
        """Find nav_graph element position."""
        if not self._graph:
            return None

        actions = self._graph.get_in_screen_actions(screen_type)
        for act in actions:
            if act.get("element", "") == element_name:
                return (act.get("x", 540), act.get("y", 960))

        # Also check other screens (element might have moved)
        for st, node in self._graph.nodes.items():
            if st == screen_type:
                continue
            for act in node.in_screen_actions:
                if act.get("element", "") == element_name:
                    return (act.get("x", 540), act.get("y", 960))

        return None

    def _find_by_intent(self, intent: str, screenshot_path: Any) -> Optional[Tuple[int, int]]:
        """Search for intent-related keywords in OCR text."""
        intent_keywords = {
            "close": ["닫기", "close", "x", "확인", "ok"],
            "confirm": ["확인", "ok", "yes", "예", "구매", "purchase"],
            "enhance": ["강화", "enhance", "upgrade", "레벨업"],
            "equip": ["장착", "equip", "착용", "장비"],
            "quest": ["퀘스트", "quest", "수락", "accept", "완료", "complete"],
            "collect_reward": ["보상", "reward", "수령", "collect", "받기"],
            "navigate": [],
            "tap_button": [],
            "select_item": [],
        }

        keywords = intent_keywords.get(intent, [])
        if not keywords:
            return None

        try:
            texts = self._read_text(screenshot_path)
            for kw in keywords:
                for text_str, conf, ty, tx in texts:
                    if isinstance(text_str, str) and kw.lower() in text_str.lower():
                        return (tx, ty)
        except Exception:
            pass

        return None

    def _complete_pattern(self, success: bool):
        """Mark pattern execution as complete."""
        if self._active_pattern:
            if success:
                self._active_pattern.success_count += 1
                print(f"[PatternExec] Pattern '{self._active_pattern.name}' COMPLETED "
                      f"(success rate: {self._active_pattern.success_rate:.0%})")
            else:
                print(f"[PatternExec] Pattern '{self._active_pattern.name}' FAILED "
                      f"(success rate: {self._active_pattern.success_rate:.0%})")

            # Save updated stats
            if self._db:
                self._db.save()

            self._active_pattern = None
            self._active_step_idx = 0
