"""
ExplorationEngine -- Autonomous UI Discovery
==============================================
Grid-tap -> pixel diff -> OCR -> record loop for discovering UI elements.
Discovers screens, elements, transitions, and dead zones automatically.

Extracted from smart_player.py with injectable dependencies.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .discovery_db import DiscoveryDB
from .safety_guard import SafetyGuard

logger = logging.getLogger(__name__)

# Type aliases for injectable callbacks
ScreenshotFn = Callable[[str], Optional[Path]]       # (label) -> screenshot path
TapFn = Callable[[int, int, float], None]             # (x, y, wait_seconds)
DetectScreenFn = Callable[[Path], str]                 # (screenshot_path) -> screen_type
ReadScreenTextFn = Callable[[Path], List[Tuple]]       # (path) -> [(text, conf, y, x), ...]
CloseOverlayFn = Callable[[int], None]                 # (max_attempts)
BacktrackFn = Callable[[str], bool]                    # (target_screen) -> success


class ExplorationEngine:
    """Grid-tap -> diff -> OCR -> record loop for discovering UI elements."""

    GRID_COLS = 5
    GRID_ROWS = 8
    CHANGE_THRESHOLD = 0.05    # 5% pixel diff = successful interaction
    MARGIN_TOP = 0.05
    MARGIN_BOTTOM = 0.08
    MAX_DEPTH = 4
    MAX_TAPS_PER_SCREEN = 20

    def __init__(
        self,
        db: DiscoveryDB,
        safety: SafetyGuard,
        screenshot_fn: ScreenshotFn,
        tap_fn: TapFn,
        detect_screen_fn: DetectScreenFn,
        read_screen_text_fn: Optional[ReadScreenTextFn] = None,
        close_overlay_fn: Optional[CloseOverlayFn] = None,
        backtrack_fn: Optional[BacktrackFn] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        """
        Args:
            db: DiscoveryDB for persistent element/transition storage.
            safety: SafetyGuard for blocking dangerous taps.
            screenshot_fn: (label) -> Path. Captures a screenshot.
            tap_fn: (x, y, wait) -> None. Taps at coordinates.
            detect_screen_fn: (screenshot_path) -> screen_type string.
            read_screen_text_fn: (path) -> [(text, conf, y, x)]. OCR full screen.
            close_overlay_fn: (max_attempts) -> None. Dismisses popup/overlay.
            backtrack_fn: (target) -> bool. Navigates to safe screen.
            screen_width: Device screen width.
            screen_height: Device screen height.
        """
        self.db = db
        self.safety = safety
        self._screenshot = screenshot_fn
        self._tap = tap_fn
        self._detect_screen = detect_screen_fn
        self._read_screen_text = read_screen_text_fn
        self._close_overlay = close_overlay_fn
        self._backtrack_fn = backtrack_fn
        self._screen_width = screen_width
        self._screen_height = screen_height

        self._depth = 0
        self._breadcrumb: List[str] = []

    def explore_current_screen(
        self,
        screen_type: str,
        max_taps: int = 20,
    ) -> Dict[str, int]:
        """
        Main exploration loop: grid tap -> diff -> OCR -> record.

        Args:
            screen_type: Current screen identifier.
            max_taps: Maximum number of taps this round.

        Returns:
            {"elements_found": N, "transitions_found": N, "taps": N}
        """
        logger.info("EXPLORE: Starting exploration of '%s' (depth=%d)", screen_type, self._depth)
        self.db.record_visit(screen_type)

        # OCR the full screen once (cache for nearest-text lookups)
        ocr_texts: List[Tuple] = []
        if self._read_screen_text:
            p = self._screenshot("explore_ocr")
            if p:
                ocr_texts = self._read_screen_text(p)

        untapped = self.db.get_untapped_regions(screen_type)
        points = self._prioritize_points(untapped, screen_type)

        elements_found = 0
        transitions_found = 0
        taps_done = 0
        effective_max = min(max_taps, self.MAX_TAPS_PER_SCREEN)

        for x, y in points[:effective_max]:
            if self.db.is_dead_zone(screen_type, x, y):
                continue
            if not self.safety.is_safe_to_tap(screen_type, x, y, ocr_texts):
                continue

            before = self._screenshot("explore_before")
            self._tap(x, y, 2.0)
            after = self._screenshot("explore_after")
            taps_done += 1

            change = self._compute_change(before, after)

            if change < self.CHANGE_THRESHOLD:
                self.db.record_failure(screen_type, x, y)
                continue

            after_screen = self._detect_screen(after) if after else "unknown"
            nearby_text = self._find_nearest_text(ocr_texts, x, y) if ocr_texts else ""
            self.db.record_element(
                screen_type, x, y, nearby_text, after_screen, success=True)
            elements_found += 1

            if after_screen != screen_type and after_screen != "unknown":
                self.db.record_transition(
                    screen_type, after_screen,
                    [{"action": "tap", "x": x, "y": y,
                      "label": nearby_text or f"btn_{x}_{y}"}])
                transitions_found += 1
                logger.info(
                    "EXPLORE: Transition %s -> %s via (%d,%d) '%s'",
                    screen_type, after_screen, x, y, nearby_text,
                )

                self._depth += 1
                if self._depth > self.MAX_DEPTH:
                    logger.info("EXPLORE: Max depth %d reached, backtracking", self.MAX_DEPTH)
                    self.backtrack()
                    self._depth = 0
                    break
                else:
                    self._try_close_and_verify(screen_type, after_screen)
                    verify = self._screenshot("explore_verify")
                    if verify:
                        verify_screen = self._detect_screen(verify)
                        if verify_screen != screen_type:
                            logger.info("EXPLORE: Screen changed to %s, stopping", verify_screen)
                            break
            else:
                logger.debug(
                    "EXPLORE: Element at (%d,%d) '%s' change=%.3f",
                    x, y, nearby_text, change,
                )

        self.db.save()
        logger.info(
            "EXPLORE: Done. %d elements, %d transitions, %d taps",
            elements_found, transitions_found, taps_done,
        )
        return {
            "elements_found": elements_found,
            "transitions_found": transitions_found,
            "taps": taps_done,
        }

    def explore_unknown_state(self) -> str:
        """Try to identify and recover from an unknown screen."""
        logger.info("EXPLORE: Unknown screen -- attempting identification")

        if self._read_screen_text:
            p = self._screenshot("unknown_id")
            if p:
                ocr_texts = self._read_screen_text(p)
                if ocr_texts:
                    all_text = " ".join(
                        t[0] for t in ocr_texts if isinstance(t, tuple)
                    )
                    logger.info("EXPLORE: OCR on unknown: '%s'", all_text[:100])

        # Try closing current overlay
        self._try_close_and_verify("unknown", "unknown")
        verify = self._screenshot("unknown_verify")
        if verify:
            screen = self._detect_screen(verify)
            if screen != "unknown":
                logger.info("EXPLORE: Recovered to '%s' after close", screen)
                return screen

        # Last resort: backtrack
        self.backtrack()
        final = self._screenshot("unknown_final")
        if final:
            screen = self._detect_screen(final)
            logger.info("EXPLORE: After backtrack, screen='%s'", screen)
            return screen if screen != "unknown" else "lobby"

        return "lobby"

    def backtrack(self, target: str = "lobby") -> bool:
        """Navigate back to a known safe screen."""
        logger.info("EXPLORE: Backtracking to '%s'", target)
        self._depth = 0
        self._breadcrumb.clear()

        if self._backtrack_fn:
            return self._backtrack_fn(target)

        # Default backtrack: try closing overlays repeatedly
        for _ in range(5):
            p = self._screenshot("bt_check")
            if not p:
                continue
            screen = self._detect_screen(p)
            if screen == target:
                logger.info("EXPLORE: Reached '%s'", target)
                return True
            if self._close_overlay:
                self._close_overlay(3)

        logger.warning("EXPLORE: Backtrack to '%s' failed", target)
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_close_and_verify(self, original_screen: str, after_screen: str) -> None:
        """Attempt to close a popup/overlay to return to original screen."""
        if self._close_overlay:
            self._close_overlay(3)

    def _generate_grid_points(self) -> List[Tuple[int, int]]:
        """Generate grid points excluding margins."""
        w, h = self._screen_width, self._screen_height
        top = int(h * self.MARGIN_TOP)
        bottom = int(h * (1.0 - self.MARGIN_BOTTOM))
        cell_w = w // self.GRID_COLS
        cell_h = (bottom - top) // self.GRID_ROWS
        points = []
        for r in range(self.GRID_ROWS):
            for c in range(self.GRID_COLS):
                cx = c * cell_w + cell_w // 2
                cy = top + r * cell_h + cell_h // 2
                points.append((cx, cy))
        return points

    def _prioritize_points(
        self,
        points: List[Tuple[int, int]],
        screen: str,
    ) -> List[Tuple[int, int]]:
        """Prioritize center and button zones."""
        if not points:
            return self._generate_grid_points()

        def priority(pt: Tuple[int, int]) -> int:
            x, y = pt
            score = 0
            # Center column bonus
            center_margin = self._screen_width * 0.2
            if center_margin < x < self._screen_width - center_margin:
                score += 2
            # Button zone (bottom area, above nav bar)
            btn_top = self._screen_height * 0.73
            btn_bottom = self._screen_height * 0.91
            if btn_top < y < btn_bottom:
                score += 3
            # Mid-screen area
            mid_top = self._screen_height * 0.42
            mid_bottom = self._screen_height * 0.63
            if mid_top < y < mid_bottom:
                score += 1
            return -score

        points.sort(key=priority)
        return points

    @staticmethod
    def _compute_change(
        before_path: Optional[Path],
        after_path: Optional[Path],
    ) -> float:
        """Compute pixel difference ratio between two screenshots."""
        if not before_path or not after_path:
            return 0.0
        try:
            from PIL import Image
            img1 = Image.open(before_path).convert("L").resize((270, 480), Image.LANCZOS)
            img2 = Image.open(after_path).convert("L").resize((270, 480), Image.LANCZOS)
            arr1 = np.array(img1, dtype=np.float64)
            arr2 = np.array(img2, dtype=np.float64)
            return float(np.abs(arr1 - arr2).mean() / 255.0)
        except Exception:
            return 0.0

    @staticmethod
    def _find_nearest_text(
        ocr_texts: List[Tuple],
        x: int,
        y: int,
        radius: int = 150,
    ) -> str:
        """Find nearest OCR text to (x, y) from cached results."""
        best = ""
        best_dist = float(radius)
        for item in ocr_texts:
            if not isinstance(item, tuple) or len(item) < 4:
                continue
            text, conf, ty, tx = item[0], item[1], item[2], item[3]
            dist = ((tx - x) ** 2 + (ty - y) ** 2) ** 0.5
            if dist < best_dist and conf > 0.3:
                best = text
                best_dist = dist
        return best
