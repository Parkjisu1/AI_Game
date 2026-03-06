"""
Pattern Recorder -- Watch & Learn from User Demonstrations
==========================================================
Monitors the device screen while the user plays, detecting screen transitions
and in-screen actions. Extracts behavior patterns (intent-based, not coordinate-based).

Usage:
    python -m virtual_player learn --package studio.gameberry.anv --pattern quest
    # User plays the game, recorder captures actions
    # Press Ctrl+C to stop recording
    # Pattern is saved to learning DB

Recording approach:
1. Take screenshots every ~1.5s
2. Detect screen type changes (= user navigated)
3. Capture touch events via getevent (= user tapped somewhere)
4. Combine: screen context + touch location + OCR text -> intent-based step
5. Post-process into ActionPattern with semantic targets
"""

import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .action_pattern import ActionStep, ActionPattern, PatternDB

logger = logging.getLogger(__name__)


class TouchEventCapture:
    """Captures touch events from ADB getevent in a background thread."""

    def __init__(self, adb_path: str, device: str):
        self._adb_path = adb_path
        self._device = device
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._touches: List[Dict] = []  # [{x, y, timestamp}, ...]
        self._lock = threading.Lock()

        # getevent state machine
        self._cur_x = 0
        self._cur_y = 0
        self._touch_down = False
        self._max_x = 32767  # default ABS range, updated on first event
        self._max_y = 32767
        self._screen_w = 1080
        self._screen_h = 1920

    def start(self, screen_w: int = 1080, screen_h: int = 1920):
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    def pop_touches(self) -> List[Dict]:
        """Get and clear all captured touches since last call."""
        with self._lock:
            touches = list(self._touches)
            self._touches.clear()
        return touches

    def _capture_loop(self):
        """Background thread: run getevent and parse touch events."""
        try:
            cmd = [self._adb_path, "-s", self._device, "shell", "getevent", "-lt"]
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in self._process.stdout:
                if not self._running:
                    break
                self._parse_line(line.strip())
        except Exception as e:
            logger.debug("TouchEventCapture error: %s", e)
        finally:
            self._running = False

    def _parse_line(self, line: str):
        """Parse a single getevent -lt line."""
        # Format: [timestamp] /dev/input/eventN: TYPE CODE VALUE
        # Example: [    1234.567890] /dev/input/event4: EV_ABS ABS_MT_POSITION_X 0000021c
        if "ABS_MT_POSITION_X" in line:
            m = re.search(r"ABS_MT_POSITION_X\s+([0-9a-fA-F]+)", line)
            if m:
                self._cur_x = int(m.group(1), 16)
        elif "ABS_MT_POSITION_Y" in line:
            m = re.search(r"ABS_MT_POSITION_Y\s+([0-9a-fA-F]+)", line)
            if m:
                self._cur_y = int(m.group(1), 16)
        elif "BTN_TOUCH" in line and "DOWN" in line:
            self._touch_down = True
        elif "BTN_TOUCH" in line and "UP" in line:
            if self._touch_down:
                # Map raw input coords to screen pixels
                screen_x = int(self._cur_x / self._max_x * self._screen_w)
                screen_y = int(self._cur_y / self._max_y * self._screen_h)
                # Clamp
                screen_x = max(0, min(self._screen_w, screen_x))
                screen_y = max(0, min(self._screen_h, screen_y))

                with self._lock:
                    self._touches.append({
                        "x": screen_x,
                        "y": screen_y,
                        "timestamp": time.time(),
                    })
            self._touch_down = False
        # Detect ABS range from ABS_MT_TRACKING_ID or similar
        elif "ABS_MAX" in line or "abs_max" in line:
            # Try to extract max values
            pass


def _region_from_coords(x: int, y: int, w: int = 1080, h: int = 1920) -> str:
    """Classify tap position into a semantic region."""
    ry = y / h
    rx = x / w
    if ry < 0.15:
        return "top"
    elif ry > 0.85:
        return "bottom"
    elif ry > 0.4 and ry < 0.6 and rx > 0.3 and rx < 0.7:
        return "center"
    elif rx < 0.3:
        return "left"
    elif rx > 0.7:
        return "right"
    return "center"


def _infer_intent(
    prev_screen: str,
    curr_screen: str,
    touch_x: int,
    touch_y: int,
    ocr_near: List[str],
    nav_graph=None,
) -> Tuple[str, str]:
    """Infer the action intent from context.

    Returns (intent, target_desc).
    """
    ocr_lower = " ".join(t.lower() for t in ocr_near)

    # Screen changed -> navigation
    if prev_screen != curr_screen and curr_screen != "unknown":
        return "navigate", f"go to {curr_screen}"

    # Close/dismiss indicators
    for kw in ["close", "닫기", "확인", "ok", "취소"]:
        if kw in ocr_lower:
            return "close", f"dismiss ({kw})"

    # Purchase/confirm
    for kw in ["구매", "purchase", "buy", "구입"]:
        if kw in ocr_lower:
            return "confirm", f"purchase ({kw})"

    # Enhance/upgrade
    for kw in ["강화", "enhance", "upgrade", "레벨업", "level up"]:
        if kw in ocr_lower:
            return "enhance", f"upgrade ({kw})"

    # Equip
    for kw in ["장착", "equip", "착용"]:
        if kw in ocr_lower:
            return "equip", f"equip item ({kw})"

    # Quest
    for kw in ["퀘스트", "quest", "임무", "mission", "완료", "complete", "수락", "accept"]:
        if kw in ocr_lower:
            return "quest", f"quest action ({kw})"

    # Reward
    for kw in ["보상", "reward", "수령", "collect", "받기"]:
        if kw in ocr_lower:
            return "collect_reward", f"collect reward ({kw})"

    # Scroll (based on region)
    region = _region_from_coords(touch_x, touch_y)

    # Item selection (tap in center area)
    if region == "center":
        return "select_item", "select item"

    # Button tap (bottom area)
    if region == "bottom":
        return "tap_button", "tap bottom button"

    return "tap_button", "general tap"


class PatternRecorder:
    """Records user demonstrations by watching the screen.

    Usage:
        recorder = PatternRecorder(...)
        recorder.start_recording("quest_1", "quest")
        # User plays on device...
        pattern = recorder.stop_recording()
        # pattern is saved to PatternDB
    """

    SCREENSHOT_INTERVAL = 1.5  # seconds between screenshots
    OCR_RADIUS = 150           # pixels around touch point to search for text

    def __init__(
        self,
        screenshot_fn: Callable[[str], Optional[Path]],
        detect_screen_fn: Callable[[Path], str],
        read_text_fn: Callable[[Path], List[Tuple[str, float, int, int]]],
        tap_fn: Optional[Callable] = None,
        pattern_db: Optional[PatternDB] = None,
        nav_graph: Any = None,
        adb_path: str = "",
        device: str = "",
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        self._screenshot = screenshot_fn
        self._detect_screen = detect_screen_fn
        self._read_text = read_text_fn
        self._tap = tap_fn
        self._db = pattern_db
        self._nav_graph = nav_graph
        self._screen_w = screen_width
        self._screen_h = screen_height

        # Touch capture
        self._touch_capture: Optional[TouchEventCapture] = None
        if adb_path and device:
            self._touch_capture = TouchEventCapture(adb_path, device)

        # Recording state
        self._recording = False
        self._current_name = ""
        self._current_category = ""
        self._steps: List[ActionStep] = []
        self._prev_screen = "unknown"
        self._prev_screenshot: Optional[Path] = None
        self._prev_texts: List[Tuple[str, float, int, int]] = []

    def start_recording(self, pattern_name: str, category: str = "general"):
        """Begin recording a new pattern demonstration."""
        self._recording = True
        self._current_name = pattern_name
        self._current_category = category
        self._steps = []
        self._prev_screen = "unknown"
        self._prev_screenshot = None
        self._prev_texts = []

        if self._touch_capture:
            self._touch_capture.start(self._screen_w, self._screen_h)

        print(f"\n[Recorder] ===== RECORDING: {pattern_name} ({category}) =====")
        print(f"[Recorder] Play the game now. Press Ctrl+C when done.")
        print(f"[Recorder] Watching screen every {self.SCREENSHOT_INTERVAL}s...\n")

    def stop_recording(self) -> Optional[ActionPattern]:
        """Stop recording and return the captured pattern."""
        self._recording = False

        if self._touch_capture:
            self._touch_capture.stop()

        if not self._steps:
            print("[Recorder] No steps captured.")
            return None

        pattern = ActionPattern(
            name=self._current_name,
            category=self._current_category,
            description=f"Learned from demo: {len(self._steps)} steps",
            trigger_screen=self._steps[0].screen_type if self._steps else "",
            steps=self._steps,
            success_screen=self._steps[-1].expected_screen or self._steps[-1].screen_type,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        # Extract trigger texts from first step
        if self._steps and self._steps[0].ocr_context:
            pattern.trigger_text = self._steps[0].ocr_context[:3]

        # Extract success texts from last step
        if self._steps and self._steps[-1].expected_text:
            pattern.success_text = self._steps[-1].expected_text[:3]

        # Save to DB
        if self._db:
            self._db.add(pattern)
            print(f"\n[Recorder] Pattern '{pattern.name}' saved to DB ({len(pattern.steps)} steps)")
        else:
            print(f"\n[Recorder] Pattern '{pattern.name}' captured ({len(pattern.steps)} steps)")
            print(f"[Recorder] WARNING: No PatternDB provided, pattern not persisted!")

        # Print summary
        self._print_pattern_summary(pattern)
        return pattern

    def record_loop(self):
        """Main recording loop -- call after start_recording().

        Blocks until self._recording is False (Ctrl+C or stop_recording).
        """
        tick = 0
        while self._recording:
            tick += 1
            try:
                self._record_tick(tick)
            except KeyboardInterrupt:
                print("\n[Recorder] Ctrl+C detected, stopping...")
                break
            except Exception as e:
                logger.debug("Recorder tick error: %s", e)

            time.sleep(self.SCREENSHOT_INTERVAL)

    def _record_tick(self, tick: int):
        """Single recording iteration."""
        # Take screenshot
        path = self._screenshot(f"learn_{tick:04d}")
        if not path or not path.exists():
            return

        # Detect screen type
        screen_type = self._detect_screen(path)

        # Read OCR text
        texts = self._read_text(path)
        text_strs = [t[0] for t in texts if isinstance(t[0], str)]

        # Get any touch events
        touches = []
        if self._touch_capture:
            touches = self._touch_capture.pop_touches()

        # Detect changes and record steps
        screen_changed = (screen_type != self._prev_screen
                          and self._prev_screen != "unknown")

        if screen_changed or touches:
            self._process_observation(
                tick=tick,
                screen_type=screen_type,
                screen_changed=screen_changed,
                texts=texts,
                text_strs=text_strs,
                touches=touches,
                screenshot_path=path,
            )

        # Update state
        self._prev_screen = screen_type
        self._prev_screenshot = path
        self._prev_texts = texts

        # Status output
        status = f"[Recorder] Tick {tick}: screen={screen_type}"
        if touches:
            for t in touches:
                status += f" | touch=({t['x']},{t['y']})"
        if screen_changed:
            status += " | SCREEN CHANGED"
        print(status)

    def _process_observation(
        self,
        tick: int,
        screen_type: str,
        screen_changed: bool,
        texts: List[Tuple],
        text_strs: List[str],
        touches: List[Dict],
        screenshot_path: Path,
    ):
        """Process a detected action and create an ActionStep."""
        # Determine touch coordinates (use touch capture or infer from transition)
        touch_x, touch_y = 540, 960  # default center

        if touches:
            # Use the most recent touch
            last_touch = touches[-1]
            touch_x = last_touch["x"]
            touch_y = last_touch["y"]
        elif screen_changed and self._nav_graph:
            # Try to infer from nav_graph edge
            edges = self._nav_graph.get_edges_from(self._prev_screen)
            for edge in edges:
                if edge.target == screen_type:
                    touch_x = edge.action.x
                    touch_y = edge.action.y
                    break

        # Find OCR text near the touch point
        ocr_near = self._get_ocr_near_point(texts, touch_x, touch_y)

        # Infer intent
        intent, target_desc = _infer_intent(
            prev_screen=self._prev_screen,
            curr_screen=screen_type,
            touch_x=touch_x,
            touch_y=touch_y,
            ocr_near=ocr_near,
            nav_graph=self._nav_graph,
        )

        # Find matching nav_graph element
        target_element = ""
        if self._nav_graph:
            target_element = self._find_nav_element(
                self._prev_screen, touch_x, touch_y)

        # Find closest OCR text as target_text
        target_text = ocr_near[0] if ocr_near else ""

        # Build the step
        step = ActionStep(
            screen_type=self._prev_screen if not screen_changed else self._prev_screen,
            ocr_context=text_strs[:5],
            intent=intent,
            target_desc=target_desc,
            target_element=target_element,
            target_text=target_text,
            target_region=_region_from_coords(touch_x, touch_y, self._screen_w, self._screen_h),
            action_type="tap",
            fallback_x=touch_x,
            fallback_y=touch_y,
            expected_screen=screen_type if screen_changed else "",
            expected_text=text_strs[:3],
            confidence=0.8 if touches else 0.5,
        )

        self._steps.append(step)
        print(f"  [STEP {len(self._steps)}] {intent}: {target_desc} "
              f"({self._prev_screen}->{screen_type if screen_changed else 'same'}) "
              f"at ({touch_x},{touch_y}) text='{target_text[:30]}'")

        # Auto-save after each step (crash-safe: pattern is saved even if process is killed)
        self._autosave()

    def _get_ocr_near_point(
        self,
        texts: List[Tuple],
        x: int,
        y: int,
    ) -> List[str]:
        """Get OCR text near a given point (within OCR_RADIUS pixels)."""
        near = []
        for text_str, conf, ty, tx in texts:
            if not isinstance(text_str, str):
                continue
            dist = ((tx - x) ** 2 + (ty - y) ** 2) ** 0.5
            if dist < self.OCR_RADIUS:
                near.append(text_str)
        return near

    def _find_nav_element(self, screen_type: str, x: int, y: int) -> str:
        """Find the nearest nav_graph element to the tap point."""
        if not self._nav_graph:
            return ""

        node = self._nav_graph.nodes.get(screen_type)
        if not node:
            return ""

        best_elem = ""
        best_dist = float("inf")

        for action in node.in_screen_actions:
            ax = action.get("x", 0)
            ay = action.get("y", 0)
            dist = ((ax - x) ** 2 + (ay - y) ** 2) ** 0.5
            if dist < best_dist and dist < 150:
                best_dist = dist
                best_elem = action.get("element", "")

        return best_elem

    def _autosave(self):
        """Save current steps to DB after each step (crash-safe)."""
        if not self._db or not self._steps:
            return
        try:
            pattern = ActionPattern(
                name=self._current_name,
                category=self._current_category,
                description=f"Learned from demo: {len(self._steps)} steps (auto-saved)",
                trigger_screen=self._steps[0].screen_type if self._steps else "",
                steps=list(self._steps),
                success_screen=self._steps[-1].expected_screen or self._steps[-1].screen_type,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            if self._steps[0].ocr_context:
                pattern.trigger_text = self._steps[0].ocr_context[:3]
            self._db.add(pattern)
        except Exception as e:
            logger.debug("Autosave failed: %s", e)

    def _print_pattern_summary(self, pattern: ActionPattern):
        """Print a readable summary of the captured pattern."""
        print(f"\n{'='*60}")
        print(f"Pattern: {pattern.name} ({pattern.category})")
        print(f"Steps: {len(pattern.steps)}")
        print(f"{'='*60}")

        for i, step in enumerate(pattern.steps):
            screen_info = f"[{step.screen_type}]"
            intent_info = f"{step.intent}: {step.target_desc}"
            target_info = ""
            if step.target_text:
                target_info = f" (text='{step.target_text[:25]}')"
            elif step.target_element:
                target_info = f" (elem={step.target_element})"
            result = ""
            if step.expected_screen:
                result = f" -> {step.expected_screen}"

            print(f"  {i+1}. {screen_info} {intent_info}{target_info}{result}")

        print(f"{'='*60}\n")
