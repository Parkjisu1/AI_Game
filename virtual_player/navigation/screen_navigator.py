"""
Screen Navigator
=================
Core navigation engine: recognize current screen -> plan path -> execute actions.
Handles unexpected screens (popups, wrong destinations) with adaptive retry.

Ported from C10+ smart_player/navigator.py -- adapted for virtual_player Brain interface.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..adb import (
    log, tap, swipe, press_back, take_screenshot,
    get_device_resolution, claude_vision_classify,
)
from .classifier import ScreenClassifier, ScreenClassification
from .nav_graph import NavigationGraph, NavEdge, NavAction
from .popup_handler import PopupHandler


@dataclass
class NavigationState:
    """Tracks the navigator's current state during a session."""
    current_screen: str = "unknown"
    last_screenshot: Optional[Path] = None
    last_classification: Optional[ScreenClassification] = None
    step_count: int = 0
    stuck_count: int = 0
    visited_screens: Dict[str, int] = field(default_factory=dict)

    def record_visit(self, screen_type: str):
        self.visited_screens[screen_type] = self.visited_screens.get(screen_type, 0) + 1


class ScreenNavigator:
    """AI-driven game navigator using screen classification + nav graph."""

    MAX_RETRIES = 3
    MAX_STEPS = 80
    STUCK_THRESHOLD = 5

    # Common close/back button positions (1080x1920 resolution)
    FALLBACK_CLOSE_POSITIONS = [
        (540, 1880),   # Bottom center X
        (540, 1850),   # Slightly higher bottom center
        (420, 1880),   # Bottom center-left X
        (1020, 80),    # Top-right X button
        (60, 80),      # Top-left back arrow
        (540, 100),    # Top center
    ]

    def __init__(
        self,
        graph: NavigationGraph,
        classifier: ScreenClassifier,
        popup_handler: PopupHandler,
        temp_dir: Path,
        screen_equivalences: Dict[str, str] = None,
    ):
        self.graph = graph
        self.classifier = classifier
        self.popup_handler = popup_handler
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._equivs = screen_equivalences or {}
        self.state = NavigationState()

    # --- Public API ---

    def take_and_classify(self) -> ScreenClassification:
        """Take a screenshot, classify it, and update state."""
        self.state.step_count += 1
        shot_path = self.temp_dir / f"nav_{self.state.step_count:04d}.png"
        take_screenshot(shot_path)
        self.state.last_screenshot = shot_path

        classification = self.classifier.classify(shot_path)
        self.state.current_screen = classification.screen_type
        self.state.last_classification = classification
        self.state.record_visit(classification.screen_type)
        return classification

    def is_equivalent(self, screen_a: str, screen_b: str) -> bool:
        """Check if two screens are equivalent (same physical location)."""
        if screen_a == screen_b:
            return True
        if self._equivs.get(screen_a) == screen_b:
            return True
        if self._equivs.get(screen_b) == screen_a:
            return True
        base_a = self._equivs.get(screen_a, screen_a)
        base_b = self._equivs.get(screen_b, screen_b)
        return base_a == base_b

    def navigate_to(self, target: str) -> bool:
        """Navigate from current screen to target screen type.

        Returns True if successfully reached the target.
        """
        if self.state.current_screen == target:
            return True

        if self.is_equivalent(self.state.current_screen, target):
            log(f"  [Nav] '{self.state.current_screen}' equivalent to '{target}'")
            return True

        for attempt in range(self.MAX_RETRIES):
            path = self.graph.find_path(self.state.current_screen, target)

            if path is None:
                log(f"  [Nav] No path: {self.state.current_screen} -> {target} "
                    f"(attempt {attempt + 1})")
                if self._explore_for_path(target):
                    return True
                continue

            log(f"  [Nav] Path found: {' -> '.join(e.target for e in path)} "
                f"({len(path)} steps)")

            if self._execute_path(path, target):
                return True

            cls = self.take_and_classify()
            log(f"  [Nav] Retry: now at {cls.screen_type}, target={target}")

        # Last resort: hub recovery
        log(f"  [Nav] All attempts failed, trying hub recovery...")
        if self._fallback_to_hub(target):
            return True

        log(f"  [Nav] FAILED to reach {target}")
        return False

    def dismiss_popups(self, max_attempts: int = 5) -> ScreenClassification:
        """Dismiss any startup popups, return final classification."""
        cls = self.take_and_classify()
        for _ in range(max_attempts):
            if self.popup_handler.is_popup(cls):
                if cls.screen_type == "popup_tutorial":
                    self.popup_handler.handle_tutorial(cls, self.state.last_screenshot)
                else:
                    self.popup_handler.dismiss(cls, self.state.last_screenshot)
                time.sleep(1.5)
                cls = self.take_and_classify()
            else:
                break
        return cls

    def reset_state(self):
        """Reset navigation state for a new session."""
        self.state = NavigationState()

    # --- Internal ---

    def _execute_path(self, path: List[NavEdge], final_target: str) -> bool:
        """Execute a sequence of navigation edges."""
        for i, edge in enumerate(path):
            prev_screen = self.state.current_screen
            self._execute_action(edge.action, edge)

            cls = self.take_and_classify()

            # Handle popup
            if self.popup_handler.is_popup(cls):
                self._handle_popup(cls)
                cls = self.take_and_classify()

            if cls.screen_type == final_target or self.is_equivalent(cls.screen_type, final_target):
                return True

            if cls.screen_type == edge.target or self.is_equivalent(cls.screen_type, edge.target):
                continue

            # Screen didn't change -- try fallback close buttons
            if cls.screen_type == prev_screen:
                log(f"  [Nav] Screen unchanged, trying fallback close buttons")
                if self._try_fallback_close(edge.target, final_target):
                    return True
                cls2 = self.take_and_classify()
                if cls2.screen_type == edge.target or self.is_equivalent(cls2.screen_type, edge.target):
                    continue
                if cls2.screen_type == final_target or self.is_equivalent(cls2.screen_type, final_target):
                    return True

            # Unexpected screen
            log(f"  [Nav] Unexpected: expected={edge.target}, got={cls.screen_type}")
            if not self._handle_unexpected(cls):
                return False

            cls = self.take_and_classify()
            if cls.screen_type == final_target or self.is_equivalent(cls.screen_type, final_target):
                return True
            if cls.screen_type != edge.target and not self.is_equivalent(cls.screen_type, edge.target):
                return False

        cls = self.take_and_classify()
        return cls.screen_type == final_target or self.is_equivalent(cls.screen_type, final_target)

    def _try_fallback_close(self, edge_target: str, final_target: str) -> bool:
        """Try common close button positions to escape current screen."""
        w, h = get_device_resolution()
        scale_x = w / 1080
        scale_y = h / 1920

        prev_screen = self.state.current_screen
        for fx, fy in self.FALLBACK_CLOSE_POSITIONS:
            x = int(fx * scale_x)
            y = int(fy * scale_y)
            tap(x, y, wait=2.0)

            cls = self.take_and_classify()
            if cls.screen_type != prev_screen:
                log(f"  [Nav] Fallback success: {prev_screen} -> {cls.screen_type}")
                if cls.screen_type == final_target or self.is_equivalent(cls.screen_type, final_target):
                    return True
                return False
        return False

    def _execute_action(self, action: NavAction, edge: NavEdge = None):
        """Execute a single navigation action via ADB."""
        if action.action_type == "tap":
            tap(action.x, action.y, wait=2.0)
        elif action.action_type == "swipe":
            swipe(action.x, action.y, action.x2, action.y2, dur=300, wait=2.0)
        elif action.action_type == "back":
            press_back(wait=2.0)
        elif action.action_type == "vision":
            self._vision_navigate(edge)

    def _vision_navigate(self, edge: NavEdge = None):
        """Use Claude Vision to decide what to tap for screen transition."""
        if not self.state.last_screenshot or not self.state.last_screenshot.exists():
            shot_path = self.temp_dir / f"vision_nav_{self.state.step_count:04d}.png"
            take_screenshot(shot_path)
            self.state.last_screenshot = shot_path

        target_screen = edge.target if edge else "next screen"
        w, h = get_device_resolution()
        prompt = (
            f"I'm playing a mobile game. Current screen type: {self.state.current_screen}. "
            f"I need to navigate to: {target_screen}.\n\n"
            f"IMPORTANT: The device screen resolution is {w}x{h} pixels. "
            f"Return coordinates in this EXACT pixel range (x: 0~{w}, y: 0~{h}).\n\n"
            f"CRITICAL RULE: If you see a quit/exit confirmation dialog "
            f"(종료하시겠습니까, 나가기, exit, quit), you MUST tap the 'No'/'취소'/'아니오' button. "
            f"NEVER tap 'Yes'/'확인'/'예' on exit/quit dialogs.\n\n"
            f"Look at this screenshot and tell me exactly where to tap to navigate to {target_screen}.\n"
            f"Return JSON: {{\"action\": \"tap\", \"x\": <pixel_x>, \"y\": <pixel_y>, "
            f"\"reason\": \"<brief explanation>\"}}\n"
            f"If swiping is needed: {{\"action\": \"swipe\", "
            f"\"x1\": <start_x>, \"y1\": <start_y>, \"x2\": <end_x>, \"y2\": <end_y>, "
            f"\"reason\": \"...\"}}"
        )

        try:
            result = claude_vision_classify(prompt, self.state.last_screenshot, model="haiku")
            if result.get("action") == "tap":
                x, y = int(result.get("x", 540)), int(result.get("y", 960))
                log(f"  [Vision Nav] Tap ({x}, {y}): {result.get('reason', '')}")
                tap(x, y, wait=2.5)
            elif result.get("action") == "swipe":
                x1 = int(result.get("x1", 540))
                y1 = int(result.get("y1", 960))
                x2 = int(result.get("x2", 540))
                y2 = int(result.get("y2", 500))
                log(f"  [Vision Nav] Swipe ({x1},{y1})->({x2},{y2}): {result.get('reason', '')}")
                swipe(x1, y1, x2, y2, dur=300, wait=2.5)
            else:
                log(f"  [Vision Nav] Unclear response, tapping center")
                tap(w // 2, h // 2, wait=2.0)
        except Exception as ex:
            log(f"  [Vision Nav] Error: {ex}, tapping center")
            w, h = get_device_resolution()
            tap(w // 2, h // 2, wait=2.0)

    def _handle_popup(self, cls: ScreenClassification):
        """Handle a popup overlay."""
        if not self.state.last_screenshot:
            return
        if cls.screen_type == "popup_tutorial":
            self.popup_handler.handle_tutorial(cls, self.state.last_screenshot)
        else:
            self.popup_handler.dismiss(cls, self.state.last_screenshot)
        time.sleep(1.0)

    def _handle_unexpected(self, cls: ScreenClassification) -> bool:
        """Handle arriving at an unexpected screen."""
        self.state.stuck_count += 1

        if self.state.stuck_count >= self.STUCK_THRESHOLD:
            log(f"  [Nav] Stuck limit reached ({self.STUCK_THRESHOLD})")
            return False

        if self.popup_handler.is_popup(cls):
            self._handle_popup(cls)
            self.state.stuck_count = max(0, self.state.stuck_count - 1)
            return True

        if cls.screen_type in self.graph.nodes and cls.screen_type != "unknown":
            log(f"  [Nav] Known screen {cls.screen_type}, can re-route")
            self.state.stuck_count = 0
            return True

        log(f"  [Nav] Unknown screen, using vision to find navigation")
        dummy_edge = NavEdge(
            source=cls.screen_type, target="lobby",
            action=NavAction(action_type="vision", description="escape unknown screen"),
            success_count=0,
        )
        self._vision_navigate(dummy_edge)
        return True

    def _explore_for_path(self, target: str) -> bool:
        """Attempt to discover a path by exploring outgoing edges."""
        edges = self.graph.get_edges_from(self.state.current_screen)
        if not edges:
            dummy_edge = NavEdge(
                source=self.state.current_screen, target=target,
                action=NavAction(action_type="vision", description=f"explore toward {target}"),
                success_count=0,
            )
            self._vision_navigate(dummy_edge)
            cls = self.take_and_classify()
            return cls.screen_type == target

        original = self.state.current_screen
        for edge in edges[:3]:
            self._execute_action(edge.action)
            cls = self.take_and_classify()

            if cls.screen_type == target:
                return True

            new_path = self.graph.find_path(cls.screen_type, target)
            if new_path is not None:
                return self._execute_path(new_path, target)

            back_edge = NavEdge(
                source=cls.screen_type, target=original,
                action=NavAction(action_type="vision", description=f"return to {original}"),
                success_count=0,
            )
            self._vision_navigate(back_edge)
            self.take_and_classify()

        return False

    def _fallback_to_hub(self, final_target: str) -> bool:
        """Last resort: vision-navigate to a hub screen, then reroute."""
        hubs = self.graph.get_hub_nodes()
        if not hubs:
            return False

        for hub in hubs:
            if hub == self.state.current_screen:
                continue

            log(f"  [Nav] Hub recovery: trying to reach '{hub}' via vision")
            w, h = get_device_resolution()

            if not self.state.last_screenshot or not self.state.last_screenshot.exists():
                shot_path = self.temp_dir / f"hub_recovery_{self.state.step_count:04d}.png"
                take_screenshot(shot_path)
                self.state.last_screenshot = shot_path

            prompt = (
                f"I'm playing a mobile game and need to go back to the main screen.\n"
                f"Current screen: {self.state.current_screen}. Target: {hub}.\n\n"
                f"IMPORTANT: Device resolution is {w}x{h} pixels.\n\n"
                f"CRITICAL: If you see a quit/exit dialog, tap 'No'/'취소'. "
                f"NEVER tap 'Yes' on exit dialogs.\n\n"
                f"Look for: back arrow, home icon, X button, or bottom navigation bar.\n"
                f"Return JSON: {{\"action\": \"tap\", \"x\": <pixel_x>, \"y\": <pixel_y>, "
                f"\"reason\": \"...\"}}"
            )

            try:
                result = claude_vision_classify(prompt, self.state.last_screenshot, model="haiku")
                if result.get("action") == "tap":
                    x, y = int(result.get("x", 540)), int(result.get("y", 960))
                    log(f"  [Nav] Hub recovery tap ({x}, {y}): {result.get('reason', '')}")
                    tap(x, y, wait=3.0)
            except Exception as ex:
                log(f"  [Nav] Hub recovery vision error: {ex}")
                continue

            cls = self.take_and_classify()

            if cls.screen_type == final_target:
                return True

            if cls.screen_type == hub:
                path = self.graph.find_path(hub, final_target)
                if path is not None:
                    return self._execute_path(path, final_target)

            path = self.graph.find_path(cls.screen_type, final_target)
            if path is not None:
                return self._execute_path(path, final_target)

        return False
