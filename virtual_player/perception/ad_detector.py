"""
Ad detection and handling: detect in-game ads, wait/skip, return to game.
============================================================================
Detects ads via:
1. Foreground app change (adb dumpsys -> different package)
2. OCR keywords ("Skip", "Install", "Download", "광고", "AD", "닫기")
3. Close button patterns (X in corners, countdown timers)
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AdState:
    """Current ad detection state."""
    is_ad: bool = False
    ad_type: str = "unknown"        # "video", "interstitial", "banner", "app_redirect"
    skip_available: bool = False
    skip_position: Optional[Tuple[int, int]] = None
    countdown_s: float = 0.0
    foreground_package: str = ""


# Keywords that indicate an ad is showing
AD_KEYWORDS_EN = {"skip", "install", "download", "get it now", "play now",
                  "free download", "ad", "advertisement", "close ad",
                  "skip ad", "continue", "sponsored"}
AD_KEYWORDS_KR = {"광고", "건너뛰기", "설치", "다운로드", "닫기", "스킵",
                  "무료 다운로드", "광고 닫기"}
AD_KEYWORDS = AD_KEYWORDS_EN | AD_KEYWORDS_KR

# Keywords for skip/close buttons
SKIP_KEYWORDS = {"skip", "x", "close", "닫기", "건너뛰기", "skip ad", "스킵"}

# Common ad SDK package prefixes
AD_PACKAGES = {
    "com.google.android.gms.ads",
    "com.unity3d.ads",
    "com.applovin",
    "com.ironsource",
    "com.facebook.ads",
    "com.vungle",
    "com.chartboost",
    "com.adcolony",
    "com.mopub",
}


class AdDetector:
    """Detects ads on screen via OCR keywords and foreground app check."""

    def __init__(self, game_package: str, adb_fn: Callable,
                 read_text_fn: Optional[Callable] = None):
        """
        Args:
            game_package: Target game package name (e.g., "studio.gameberry.anv")
            adb_fn: callable(cmd) -> str for running ADB commands
            read_text_fn: callable(screenshot_path) -> [(text, conf, y, x), ...]
        """
        self._game_package = game_package
        self._adb_fn = adb_fn
        self._read_text_fn = read_text_fn

    def detect(self, screenshot_path: Optional[str] = None,
               ocr_texts: Optional[List[str]] = None) -> AdState:
        """
        Check if an ad is currently displayed.

        Args:
            screenshot_path: Current screenshot for OCR analysis
            ocr_texts: Pre-extracted OCR texts (skip OCR if provided)

        Returns:
            AdState with detection results
        """
        state = AdState()

        # Check 1: Foreground app differs from game
        fg_pkg = self._get_foreground_package()
        state.foreground_package = fg_pkg
        if fg_pkg and fg_pkg != self._game_package:
            # Check if it's an ad SDK package
            if any(fg_pkg.startswith(ad_pkg) for ad_pkg in AD_PACKAGES):
                state.is_ad = True
                state.ad_type = "app_redirect"
                logger.info("Ad detected: app redirect to %s", fg_pkg)
                return state
            # Browser or store redirect
            if any(kw in fg_pkg for kw in ("browser", "chrome", "vending", "playstore")):
                state.is_ad = True
                state.ad_type = "app_redirect"
                return state

        # Check 2: OCR keyword matching
        if ocr_texts is None and screenshot_path and self._read_text_fn:
            try:
                raw = self._read_text_fn(screenshot_path)
                ocr_texts = [t[0].lower() if isinstance(t[0], str) else "" for t in raw]
            except Exception:
                ocr_texts = []

        if ocr_texts:
            all_text = " ".join(t.lower() for t in ocr_texts)
            ad_hits = sum(1 for kw in AD_KEYWORDS if kw in all_text)
            if ad_hits >= 2:  # require 2+ keyword matches to reduce false positives
                state.is_ad = True
                state.ad_type = "interstitial"

            # Find skip button position
            if state.is_ad and self._read_text_fn and screenshot_path:
                skip_pos = self._find_skip_button(screenshot_path)
                if skip_pos:
                    state.skip_available = True
                    state.skip_position = skip_pos

            # Detect countdown ("5", "4", "3" alone, or "0:05")
            for text in ocr_texts:
                if re.match(r'^[0-5]$', text.strip()) or re.match(r'^0:\d{2}$', text.strip()):
                    state.ad_type = "video"
                    try:
                        state.countdown_s = float(re.search(r'\d+', text).group())
                    except (AttributeError, ValueError):
                        pass

        return state

    def _get_foreground_package(self) -> str:
        """Get current foreground app package name."""
        try:
            result = self._adb_fn("shell dumpsys activity activities | grep mResumedActivity")
            # Parse: mResumedActivity: ActivityRecord{... com.package/.Activity ...}
            match = re.search(r'(\S+)/\S+', result)
            if match:
                pkg = match.group(1)
                # Clean up: sometimes has extra chars
                pkg = pkg.strip().split()[-1]
                return pkg
        except Exception:
            pass
        return ""

    def _find_skip_button(self, screenshot_path: str) -> Optional[Tuple[int, int]]:
        """Find skip/close button position via OCR text location."""
        if not self._read_text_fn:
            return None
        try:
            raw = self._read_text_fn(screenshot_path)
            for text, conf, y, x in raw:
                if isinstance(text, str) and text.strip().lower() in SKIP_KEYWORDS:
                    return (int(x), int(y))
        except Exception:
            pass
        return None


class AdHandler:
    """Handles ads: wait, skip, and return to game."""

    MAX_AD_WAIT_S = 35.0        # max time to wait for ad to finish
    SKIP_CHECK_INTERVAL = 2.0   # check for skip button every N seconds
    CORNER_X_POSITIONS = [       # common close button positions (x, y)
        (1040, 40),   # top-right X
        (40, 40),     # top-left X
        (1040, 80),   # top-right slightly lower
        (540, 1850),  # bottom center "Continue"
    ]

    def __init__(self, game_package: str, launch_activity: str,
                 adb_fn: Callable, tap_fn: Callable,
                 screenshot_fn: Optional[Callable] = None,
                 detector: Optional[AdDetector] = None):
        """
        Args:
            game_package: e.g., "studio.gameberry.anv"
            launch_activity: e.g., "com.unity3d.player.UnityPlayerActivity"
            adb_fn: ADB command runner
            tap_fn: (x, y, wait) tap function
            screenshot_fn: (label) -> path screenshot function
            detector: AdDetector instance
        """
        self._game_package = game_package
        self._launch_activity = launch_activity
        self._adb_fn = adb_fn
        self._tap = tap_fn
        self._screenshot = screenshot_fn
        self._detector = detector

    def handle_ad(self, ad_state: AdState) -> str:
        """
        Handle a detected ad. Returns description of action taken.

        Strategies:
        1. App redirect -> press back to return to game
        2. Video ad -> wait for countdown, then tap skip
        3. Interstitial -> find and tap close/skip button
        4. Timeout -> force return to game via am start
        """
        if not ad_state.is_ad:
            return "no_ad"

        logger.info("Handling ad: type=%s, skip=%s", ad_state.ad_type, ad_state.skip_available)
        start = time.time()

        # Strategy 1: App redirect -- just press back
        if ad_state.ad_type == "app_redirect":
            self._adb_fn("shell input keyevent KEYCODE_BACK")
            time.sleep(1.0)
            # Check if we're back in game
            if not self._is_game_foreground():
                self._force_return_to_game()
            return "ad:back_from_redirect"

        # Strategy 2: Video ad -- wait for countdown, then skip
        if ad_state.ad_type == "video":
            wait_time = max(ad_state.countdown_s, 5.0)
            logger.info("Video ad: waiting %.0fs for skip", wait_time)
            time.sleep(wait_time)

        # Strategy 3: Try to find and tap skip/close button
        elapsed = time.time() - start
        while elapsed < self.MAX_AD_WAIT_S:
            # Try skip position if known
            if ad_state.skip_available and ad_state.skip_position:
                self._tap(ad_state.skip_position[0], ad_state.skip_position[1], 1.0)
                if self._is_game_foreground():
                    return "ad:skipped"

            # Try common close button positions
            for x, y in self.CORNER_X_POSITIONS:
                self._tap(x, y, 0.5)

            time.sleep(self.SKIP_CHECK_INTERVAL)

            # Re-detect to check if ad is gone
            if self._is_game_foreground():
                return "ad:closed"

            # Re-scan for skip button
            if self._screenshot and self._detector:
                try:
                    path = self._screenshot("ad_check")
                    new_state = self._detector.detect(str(path))
                    if not new_state.is_ad:
                        return "ad:finished"
                    if new_state.skip_available and new_state.skip_position:
                        self._tap(new_state.skip_position[0], new_state.skip_position[1], 1.0)
                except Exception:
                    pass

            elapsed = time.time() - start

        # Strategy 4: Timeout -- force return
        logger.warning("Ad timeout (%.0fs), forcing game return", elapsed)
        self._force_return_to_game()
        return "ad:force_return"

    def _is_game_foreground(self) -> bool:
        """Check if the game is currently in the foreground."""
        try:
            result = self._adb_fn("shell dumpsys activity activities | grep mResumedActivity")
            return self._game_package in result
        except Exception:
            return False

    def _force_return_to_game(self):
        """Force return to game via am start."""
        try:
            self._adb_fn("shell input keyevent KEYCODE_BACK")
            time.sleep(0.5)
            self._adb_fn("shell input keyevent KEYCODE_BACK")
            time.sleep(0.5)
            if not self._is_game_foreground():
                cmd = (f"shell am start -n "
                       f"{self._game_package}/{self._launch_activity}")
                self._adb_fn(cmd)
                time.sleep(3.0)
            logger.info("Forced return to game: %s", self._game_package)
        except Exception as e:
            logger.error("Force return failed: %s", e)
