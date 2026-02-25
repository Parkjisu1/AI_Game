"""
Smart Navigator
================
Core navigation engine: recognize current screen -> plan path -> execute actions.
Handles unexpected screens (popups, wrong destinations) with adaptive retry.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict

from core import (
    log, tap, swipe, press_back, take_screenshot, get_device_resolution,
)
from smart_player.classifier import ScreenClassifier, ScreenClassification
from smart_player.nav_graph import NavigationGraph, NavEdge, NavAction
from smart_player.popup_handler import PopupHandler


@dataclass
class NavigationState:
    """Tracks the navigator's current state during a mission."""
    current_screen: str = "unknown"
    last_screenshot: Optional[Path] = None
    step_count: int = 0
    stuck_count: int = 0          # Consecutive failures to make progress
    visited_screens: Dict[str, int] = field(default_factory=dict)
    screenshots_taken: Dict[str, List[Path]] = field(default_factory=dict)

    def record_visit(self, screen_type: str, screenshot_path: Path):
        self.visited_screens[screen_type] = self.visited_screens.get(screen_type, 0) + 1
        self.screenshots_taken.setdefault(screen_type, []).append(screenshot_path)


class SmartNavigator:
    """AI-driven game navigator using screen classification + nav graph."""

    MAX_RETRIES = 3
    MAX_STEPS = 80        # Safety limit per mission (~20s/step = ~27min max)
    STUCK_THRESHOLD = 5   # Consecutive no-progress steps before giving up

    def __init__(
        self,
        graph: NavigationGraph,
        classifier: ScreenClassifier,
        popup_handler: PopupHandler,
        session_dir: Path,
        temp_dir: Path,
        screen_equivalences: Dict[str, str] = None,
    ):
        self.graph = graph
        self.classifier = classifier
        self.popup_handler = popup_handler
        self.session_dir = session_dir
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        # Screen equivalences: e.g. {"battle": "lobby"} means battle ≈ lobby
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
        return classification

    def capture_for_mission(self, screen_type: str, shot_name: str) -> Path:
        """Take a named screenshot for the mission output and record visit."""
        shot_path = self.session_dir / f"{shot_name}.png"
        take_screenshot(shot_path)
        self.state.record_visit(screen_type, shot_path)
        return shot_path

    def _is_equivalent(self, screen_a: str, screen_b: str) -> bool:
        """Check if two screens are equivalent (same physical location).

        e.g. 'battle' and 'lobby' in idle RPGs are both the field screen.
        """
        if screen_a == screen_b:
            return True
        # Check direct equivalence
        if self._equivs.get(screen_a) == screen_b:
            return True
        if self._equivs.get(screen_b) == screen_a:
            return True
        # Check both map to the same base screen
        base_a = self._equivs.get(screen_a, screen_a)
        base_b = self._equivs.get(screen_b, screen_b)
        return base_a == base_b

    def navigate_to(self, target: str) -> bool:
        """Navigate from current screen to target screen type.

        Returns True if successfully reached the target.
        """
        if self.state.current_screen == target:
            return True

        # Check screen equivalence (e.g. battle ≈ lobby in idle RPGs)
        if self._is_equivalent(self.state.current_screen, target):
            log(f"  [Nav] Screen '{self.state.current_screen}' is equivalent to '{target}', treating as reached")
            return True

        for attempt in range(self.MAX_RETRIES):
            path = self.graph.find_path(self.state.current_screen, target)

            if path is None:
                log(f"  [Nav] No path: {self.state.current_screen} -> {target} "
                    f"(attempt {attempt + 1})")
                # Try explore mode to discover a path
                if self._explore_for_path(target):
                    return True
                continue

            log(f"  [Nav] Path found: {' -> '.join(e.target for e in path)} "
                f"({len(path)} steps)")

            if self._execute_path(path, target):
                return True

            # Path execution failed, re-classify and retry
            cls = self.take_and_classify()
            log(f"  [Nav] Retry: now at {cls.screen_type}, target={target}")

        # Last resort: try hub recovery — go to a well-connected hub, then reroute
        log(f"  [Nav] All attempts failed, trying hub recovery...")
        if self._fallback_to_hub(target):
            return True

        log(f"  [Nav] FAILED to reach {target} after {self.MAX_RETRIES} attempts + hub recovery")
        return False

    def ensure_at_screen(self, expected: str) -> bool:
        """Verify we're at the expected screen, handle popups if not."""
        cls = self.take_and_classify()
        if cls.screen_type == expected:
            return True

        # Handle popup
        if self.popup_handler.is_popup(cls):
            self._handle_popup(cls)
            cls = self.take_and_classify()
            return cls.screen_type == expected

        return False

    # --- Internal ---

    # Common close/back button positions (1080x1920 resolution)
    # Tried in order when Vision Nav fails to change screen
    FALLBACK_CLOSE_POSITIONS = [
        (540, 1880),   # Bottom center X (shop/menu close)
        (540, 1850),   # Slightly higher bottom center
        (420, 1880),   # Bottom center-left X
        (1020, 80),    # Top-right X button
        (60, 80),      # Top-left back arrow
        (540, 100),    # Top center (some games)
    ]

    def _execute_path(self, path: List[NavEdge], final_target: str) -> bool:
        """Execute a sequence of navigation edges."""
        for i, edge in enumerate(path):
            prev_screen = self.state.current_screen
            self._execute_action(edge.action, edge)

            cls = self.take_and_classify()

            # Check if we hit a popup
            if self.popup_handler.is_popup(cls):
                self._handle_popup(cls)
                cls = self.take_and_classify()

            if cls.screen_type == final_target or self._is_equivalent(cls.screen_type, final_target):
                return True

            if cls.screen_type == edge.target or self._is_equivalent(cls.screen_type, edge.target):
                continue  # On track (or equivalent)

            # Screen didn't change — try fallback close buttons before giving up
            if cls.screen_type == prev_screen:
                log(f"  [Nav] Screen unchanged after vision nav, trying fallback close buttons")
                if self._try_fallback_close(edge.target, final_target):
                    return True
                # Check if fallback got us to edge target
                cls2 = self.take_and_classify()
                if cls2.screen_type == edge.target or self._is_equivalent(cls2.screen_type, edge.target):
                    continue
                if cls2.screen_type == final_target or self._is_equivalent(cls2.screen_type, final_target):
                    return True

            # Unexpected screen
            log(f"  [Nav] Unexpected: expected={edge.target}, got={cls.screen_type}")
            if not self._handle_unexpected(cls):
                return False

            # Re-check after handling
            cls = self.take_and_classify()
            if cls.screen_type == final_target or self._is_equivalent(cls.screen_type, final_target):
                return True
            if cls.screen_type != edge.target and not self._is_equivalent(cls.screen_type, edge.target):
                return False  # Still wrong, abort path

        # Check final state
        cls = self.take_and_classify()
        return cls.screen_type == final_target or self._is_equivalent(cls.screen_type, final_target)

    def _try_fallback_close(self, edge_target: str, final_target: str) -> bool:
        """Try common close button positions to escape current screen."""
        w, h = get_device_resolution()
        scale_x = w / 1080
        scale_y = h / 1920

        prev_screen = self.state.current_screen
        for fx, fy in self.FALLBACK_CLOSE_POSITIONS:
            x = int(fx * scale_x)
            y = int(fy * scale_y)
            log(f"  [Nav] Fallback tap ({x}, {y})")
            tap(x, y, wait=2.0)

            cls = self.take_and_classify()
            if cls.screen_type != prev_screen:
                log(f"  [Nav] Fallback success: {prev_screen} -> {cls.screen_type}")
                if cls.screen_type == final_target or self._is_equivalent(cls.screen_type, final_target):
                    return True
                if cls.screen_type == edge_target or self._is_equivalent(cls.screen_type, edge_target):
                    return False  # Not final target, but screen changed — let caller continue
                return False  # Screen changed, caller should reassess
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
        from core import claude_vision_classify
        import json as _json

        if not self.state.last_screenshot or not self.state.last_screenshot.exists():
            # Take a fresh screenshot
            shot_path = self.temp_dir / f"vision_nav_{self.state.step_count:04d}.png"
            take_screenshot(shot_path)
            self.state.last_screenshot = shot_path

        target_screen = edge.target if edge else "next screen"
        w, h = get_device_resolution()
        prompt = (
            f"I'm playing a mobile game. Current screen type: {self.state.current_screen}. "
            f"I need to navigate to: {target_screen}.\n\n"
            f"IMPORTANT: The device screen resolution is {w}x{h} pixels. "
            f"Return coordinates in this EXACT pixel range (x: 0~{w}, y: 0~{h}). "
            f"Do NOT return scaled-down coordinates.\n\n"
            f"CRITICAL RULE: If you see a quit/exit confirmation dialog "
            f"(종료하시겠습니까, 나가기, exit, quit), you MUST tap the 'No'/'취소'/'아니오' button. "
            f"NEVER tap 'Yes'/'확인'/'예' on exit/quit dialogs.\n\n"
            f"Look at this screenshot and tell me exactly where to tap to navigate to {target_screen}.\n"
            f"Tips: Look for close/X buttons (often at bottom center or top right), "
            f"back arrows (top left), or navigation tabs/icons on the sides.\n"
            f"Return JSON: {{\"action\": \"tap\", \"x\": <pixel_x>, \"y\": <pixel_y>, "
            f"\"reason\": \"<brief explanation>\"}}\n"
            f"If you think swiping is needed: {{\"action\": \"swipe\", "
            f"\"x1\": <start_x>, \"y1\": <start_y>, \"x2\": <end_x>, \"y2\": <end_y>, "
            f"\"reason\": \"...\"}}\n"
            f"If unsure, tap the most likely navigation button or menu icon."
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
                # Fallback: tap center
                log(f"  [Vision Nav] Unclear response, tapping center")
                tap(540, 960, wait=2.0)
        except Exception as ex:
            log(f"  [Vision Nav] Error: {ex}, tapping center")
            tap(540, 960, wait=2.0)

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
        """Handle arriving at an unexpected screen.

        Returns True if recovered to a usable state.
        """
        self.state.stuck_count += 1

        if self.state.stuck_count >= self.STUCK_THRESHOLD:
            log(f"  [Nav] Stuck limit reached ({self.STUCK_THRESHOLD})")
            return False

        # 1. Popup? Dismiss it
        if self.popup_handler.is_popup(cls):
            self._handle_popup(cls)
            self.state.stuck_count = max(0, self.state.stuck_count - 1)
            return True

        # 2. Known screen in graph? We can re-route from here
        if cls.screen_type in self.graph.nodes and cls.screen_type != "unknown":
            log(f"  [Nav] Known screen {cls.screen_type}, can re-route")
            self.state.stuck_count = 0
            return True

        # 3. Unknown screen — try vision tap instead of back (back triggers quit dialogs)
        log(f"  [Nav] Unknown screen, using vision to find navigation")
        dummy_edge = NavEdge(
            source=cls.screen_type, target="battle",
            action=NavAction(action_type="vision", description="escape unknown screen"),
            success_count=0,
        )
        self._vision_navigate(dummy_edge)
        return True

    def _explore_for_path(self, target: str) -> bool:
        """Attempt to discover a path by exploring outgoing edges.

        When no path exists in the graph, try tapping known UI elements
        to discover new screen transitions.
        """
        # Get edges from current screen
        edges = self.graph.get_edges_from(self.state.current_screen)
        if not edges:
            # No edges at all — use vision to find a way
            dummy_edge = NavEdge(
                source=self.state.current_screen, target=target,
                action=NavAction(action_type="vision", description=f"explore toward {target}"),
                success_count=0,
            )
            self._vision_navigate(dummy_edge)
            cls = self.take_and_classify()
            if cls.screen_type == target:
                return True
            return False

        # Try each outgoing edge hoping to find a path to target
        original = self.state.current_screen
        for edge in edges[:3]:  # Limit exploration
            self._execute_action(edge.action)
            cls = self.take_and_classify()

            if cls.screen_type == target:
                return True

            # Check if from new screen we can now find a path
            new_path = self.graph.find_path(cls.screen_type, target)
            if new_path is not None:
                return self._execute_path(new_path, target)

            # Try to navigate back to original screen via vision
            back_edge = NavEdge(
                source=cls.screen_type, target=original,
                action=NavAction(action_type="vision", description=f"return to {original}"),
                success_count=0,
            )
            self._vision_navigate(back_edge)
            self.take_and_classify()

        return False

    def _fallback_to_hub(self, final_target: str) -> bool:
        """Last resort: use Vision to navigate to a hub screen, then reroute.

        Hub screens (lobby, menu_inventory) are well-connected nodes.
        We ask Claude Vision to find a "home" or "back" button to get there.
        """
        # Identify hub nodes — those with the most outgoing edges
        edge_counts = {}
        for edge in self.graph.edges:
            edge_counts[edge.source] = edge_counts.get(edge.source, 0) + 1

        # Prefer lobby, menu_inventory, then highest-connected nodes
        hub_priority = ["lobby", "menu_inventory", "menu_shop"]
        hubs = [h for h in hub_priority if h in self.graph.nodes]
        if not hubs:
            # Fall back to the most connected node
            sorted_nodes = sorted(edge_counts.items(), key=lambda x: x[1], reverse=True)
            hubs = [n for n, _ in sorted_nodes[:3] if n != self.state.current_screen]

        for hub in hubs:
            if hub == self.state.current_screen:
                continue

            log(f"  [Nav] Hub recovery: trying to reach hub '{hub}' via vision")

            # Use vision to look for home/back button
            w, h = get_device_resolution()
            from core import claude_vision_classify

            if not self.state.last_screenshot or not self.state.last_screenshot.exists():
                shot_path = self.temp_dir / f"hub_recovery_{self.state.step_count:04d}.png"
                take_screenshot(shot_path)
                self.state.last_screenshot = shot_path

            prompt = (
                f"I'm playing a mobile game and need to go back to the main screen or home screen.\n"
                f"Current screen: {self.state.current_screen}. Target: {hub}.\n\n"
                f"IMPORTANT: Device resolution is {w}x{h} pixels. "
                f"Return coordinates in range (x: 0~{w}, y: 0~{h}).\n\n"
                f"CRITICAL: If you see a quit/exit dialog, tap 'No'/'취소'/'아니오'. "
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

            # Check where we ended up
            cls = self.take_and_classify()

            if cls.screen_type == final_target:
                return True

            if cls.screen_type == hub:
                # Made it to hub, now try to route to final target
                path = self.graph.find_path(hub, final_target)
                if path is not None:
                    return self._execute_path(path, final_target)

            # Even if we're not at the hub, check if we can now find a path
            path = self.graph.find_path(cls.screen_type, final_target)
            if path is not None:
                return self._execute_path(path, final_target)

        return False

    def reset_state(self):
        """Reset navigation state for a new mission."""
        self.state = NavigationState()
