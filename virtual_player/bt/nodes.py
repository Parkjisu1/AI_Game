"""
BT Node Types
==============
Minimal Behavior Tree implementation:
  - Leaf nodes: Action, Condition, VisionQuery, DiscoveryTap
  - Composite nodes: Selector (OR), Sequence (AND)
  - Decorator: PersonaGate (persona parameter threshold check)

All nodes return Status: SUCCESS, FAILURE, RUNNING.
"""

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class Status(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


@dataclass
class BTContext:
    """Shared context passed to all BT nodes during a tick."""
    screen_type: str
    screenshot_path: Any  # Path
    persona: Any  # Persona dataclass
    tap_fn: Callable[[int, int, float], None]
    swipe_fn: Optional[Callable[[int, int, int, int, float], None]] = None
    back_fn: Optional[Callable[[], None]] = None
    snapshot: Dict[str, Any] = field(default_factory=dict)
    ocr_texts: List[str] = field(default_factory=list)
    vision_fn: Optional[Callable] = None  # async Claude Haiku query
    outcome_tracker: Any = None  # OutcomeTracker
    tick_count: int = 0
    screen_width: int = 1080
    screen_height: int = 1920


class BTNode:
    """Base class for all BT nodes."""

    def __init__(self, name: str = ""):
        self.name = name

    def tick(self, ctx: BTContext) -> Status:
        raise NotImplementedError

    def reset(self):
        """Reset node state (called when parent re-evaluates)."""
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name!r})"


# ============================================================
# Composite Nodes
# ============================================================

class Selector(BTNode):
    """Try children in order. Return SUCCESS on first success, FAILURE if all fail."""

    def __init__(self, name: str, children: List[BTNode]):
        super().__init__(name)
        self.children = children
        self._running_idx = 0

    def tick(self, ctx: BTContext) -> Status:
        for i in range(self._running_idx, len(self.children)):
            status = self.children[i].tick(ctx)
            if status == Status.RUNNING:
                self._running_idx = i
                return Status.RUNNING
            if status == Status.SUCCESS:
                self._running_idx = 0
                return Status.SUCCESS
        self._running_idx = 0
        return Status.FAILURE

    def reset(self):
        self._running_idx = 0
        for child in self.children:
            child.reset()


class Sequence(BTNode):
    """Run children in order. Return FAILURE on first failure, SUCCESS if all succeed."""

    def __init__(self, name: str, children: List[BTNode]):
        super().__init__(name)
        self.children = children
        self._running_idx = 0

    def tick(self, ctx: BTContext) -> Status:
        for i in range(self._running_idx, len(self.children)):
            status = self.children[i].tick(ctx)
            if status == Status.RUNNING:
                self._running_idx = i
                return Status.RUNNING
            if status == Status.FAILURE:
                self._running_idx = 0
                return Status.FAILURE
        self._running_idx = 0
        return Status.SUCCESS

    def reset(self):
        self._running_idx = 0
        for child in self.children:
            child.reset()


# ============================================================
# Decorator Nodes
# ============================================================

class PersonaGate(BTNode):
    """Only execute child if persona parameter meets threshold.

    Example: PersonaGate("spend_gate", "spend_threshold", ">", 0.5, buy_action)
    """

    def __init__(self, name: str, param: str, op: str, threshold: float, child: BTNode):
        super().__init__(name)
        self.param = param
        self.op = op
        self.threshold = threshold
        self.child = child

    def tick(self, ctx: BTContext) -> Status:
        persona = ctx.persona
        if persona is None:
            return self.child.tick(ctx)

        # Get param from persona.skill or persona.metadata
        val = getattr(persona.skill, self.param, None)
        if val is None:
            val = persona.metadata.get(self.param, 0.5)

        passed = False
        if self.op == ">":
            passed = val > self.threshold
        elif self.op == "<":
            passed = val < self.threshold
        elif self.op == ">=":
            passed = val >= self.threshold
        elif self.op == "<=":
            passed = val <= self.threshold

        if passed:
            return self.child.tick(ctx)
        return Status.FAILURE

    def reset(self):
        self.child.reset()


class EpsilonRandom(BTNode):
    """With probability epsilon, pick a random child instead of the first.
    Implements noise injection for play diversity."""

    def __init__(self, name: str, children: List[BTNode], epsilon: float = 0.1):
        super().__init__(name)
        self.children = children
        self.epsilon = epsilon

    def tick(self, ctx: BTContext) -> Status:
        if not self.children:
            return Status.FAILURE

        if random.random() < self.epsilon:
            child = random.choice(self.children)
            logger.debug("EpsilonRandom: random pick -> %s", child.name)
            return child.tick(ctx)

        # Default: try in order (Selector behavior)
        for child in self.children:
            status = child.tick(ctx)
            if status in (Status.SUCCESS, Status.RUNNING):
                return status
        return Status.FAILURE


# ============================================================
# Leaf Nodes
# ============================================================

class TapAction(BTNode):
    """Tap at specific coordinates."""

    def __init__(self, name: str, x: int, y: int, wait: float = 1.0):
        super().__init__(name)
        self.x = x
        self.y = y
        self.wait = wait

    def tick(self, ctx: BTContext) -> Status:
        ctx.tap_fn(self.x, self.y, self.wait)
        if ctx.outcome_tracker:
            ctx.outcome_tracker.record_attempt(
                ctx.screen_type, self.name, (self.x, self.y))
        logger.info("TapAction: %s at (%d, %d)", self.name, self.x, self.y)
        return Status.SUCCESS


class SwipeAction(BTNode):
    """Swipe from (x1,y1) to (x2,y2)."""

    def __init__(self, name: str, x1: int, y1: int, x2: int, y2: int, wait: float = 1.5):
        super().__init__(name)
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.wait = wait

    def tick(self, ctx: BTContext) -> Status:
        if ctx.swipe_fn:
            ctx.swipe_fn(self.x1, self.y1, self.x2, self.y2, self.wait)
        else:
            ctx.tap_fn(self.x1, self.y1, self.wait)
        return Status.SUCCESS


class WaitAction(BTNode):
    """Wait for a fixed duration."""

    def __init__(self, name: str, seconds: float):
        super().__init__(name)
        self.seconds = seconds

    def tick(self, ctx: BTContext) -> Status:
        time.sleep(self.seconds)
        return Status.SUCCESS


class BackKeyAction(BTNode):
    """Press Android back key."""

    def __init__(self, name: str = "back_key"):
        super().__init__(name)

    def tick(self, ctx: BTContext) -> Status:
        if ctx.back_fn:
            ctx.back_fn()
            return Status.SUCCESS
        return Status.FAILURE


class Condition(BTNode):
    """Check a condition from snapshot. Returns SUCCESS if true, FAILURE otherwise."""

    def __init__(self, name: str, key: str, op: str, value: Any):
        super().__init__(name)
        self.key = key
        self.op = op
        self.value = value

    def tick(self, ctx: BTContext) -> Status:
        actual = ctx.snapshot.get(self.key)
        if actual is None:
            return Status.FAILURE

        result = False
        if self.op == ">":
            result = actual > self.value
        elif self.op == "<":
            result = actual < self.value
        elif self.op == ">=":
            result = actual >= self.value
        elif self.op == "==":
            result = actual == self.value
        elif self.op == "!=":
            result = actual != self.value
        elif self.op == "in":
            result = actual in self.value
        elif self.op == "contains":
            result = self.value in str(actual).lower()

        return Status.SUCCESS if result else Status.FAILURE


class DiscoveryTap(BTNode):
    """Grid-based discovery: tap unexplored regions systematically."""

    def __init__(self, name: str = "discovery", cols: int = 5, rows: int = 8):
        super().__init__(name)
        self.cols = cols
        self.rows = rows
        self._index = 0

    def tick(self, ctx: BTContext) -> Status:
        cell_w = ctx.screen_width // self.cols
        cell_h = ctx.screen_height // self.rows

        col = self._index % self.cols
        row = (self._index // self.cols) % self.rows

        x = col * cell_w + cell_w // 2
        y = row * cell_h + cell_h // 2

        ctx.tap_fn(x, y, 0.8)
        self._index += 1
        logger.info("DiscoveryTap: grid[%d,%d] at (%d,%d)", col, row, x, y)
        return Status.SUCCESS

    def reset(self):
        self._index = 0


class VisionQuery(BTNode):
    """Ask Claude Haiku what to do on the current screen.

    If vision_fn is available, sends screenshot and gets (action, x, y) back.
    Tracks last tap for failed-tap feedback.
    """

    # Class-level tracking of last vision tap (shared across instances)
    last_tap: Optional[Dict[str, Any]] = None

    def __init__(self, name: str = "vision_query"):
        super().__init__(name)

    def tick(self, ctx: BTContext) -> Status:
        if ctx.vision_fn is None:
            return Status.FAILURE

        try:
            result = ctx.vision_fn(ctx.screenshot_path, ctx.screen_type, ctx.ocr_texts)
            if result is None:
                return Status.FAILURE

            action_type = result.get("action", "tap")
            x = result.get("x", ctx.screen_width // 2)
            y = result.get("y", ctx.screen_height // 2)
            description = result.get("description", "vision_action")

            if action_type == "tap":
                ctx.tap_fn(x, y, 1.5)
                VisionQuery.last_tap = {"x": x, "y": y, "description": description}
                print(f"[Vision] tap ({x},{y}): {description}")
            elif action_type == "back" and ctx.back_fn:
                ctx.back_fn()
                VisionQuery.last_tap = None
            elif action_type == "wait":
                time.sleep(result.get("seconds", 2.0))
                VisionQuery.last_tap = None
            else:
                ctx.tap_fn(x, y, 1.5)
                VisionQuery.last_tap = {"x": x, "y": y, "description": description}

            if ctx.outcome_tracker:
                ctx.outcome_tracker.record_vision_action(
                    ctx.screen_type, description, (x, y), action_type)

            return Status.SUCCESS

        except Exception as e:
            logger.warning("VisionQuery: error: %s", e)
            return Status.FAILURE
