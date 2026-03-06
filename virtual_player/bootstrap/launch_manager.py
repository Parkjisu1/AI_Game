"""
LaunchManager -- ADB Package Launch + Wait-for-Ready
=====================================================
Launches a game via ADB monkey, waits for the main activity,
and handles initial popups.
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)


class LaunchManager:
    """Manages ADB game launch and initial readiness."""

    DEFAULT_LAUNCH_TIMEOUT = 30  # seconds
    POPUP_DISMISS_ATTEMPTS = 5

    def __init__(
        self,
        adb_path: str = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        device: str = "emulator-5554",
        screenshot_fn: Optional[Callable[[str], Optional[Path]]] = None,
        tap_fn: Optional[Callable[[int, int, float], None]] = None,
    ):
        self.adb_path = adb_path
        self.device = device
        self._screenshot = screenshot_fn
        self._tap = tap_fn

    def _adb(self, args: list, timeout: int = 10) -> subprocess.CompletedProcess:
        """Run an ADB command."""
        cmd = [self.adb_path, "-s", self.device] + args
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            logger.warning("ADB command timed out: %s", " ".join(args))
            return subprocess.CompletedProcess(cmd, 1, "", "timeout")

    def launch(
        self,
        package_name: str,
        timeout: int = DEFAULT_LAUNCH_TIMEOUT,
    ) -> bool:
        """
        Launch a game package and wait for it to become ready.

        Args:
            package_name: Android package name (e.g. "com.grandgames.carmatch").
            timeout: Max seconds to wait for ready.

        Returns:
            True if launched and ready, False otherwise.
        """
        logger.info("Launching %s ...", package_name)

        # Force stop any existing instance
        self._adb(["shell", "am", "force-stop", package_name])
        time.sleep(1)

        # Launch via monkey (most reliable method)
        result = self._adb(
            ["shell", "monkey", "-p", package_name,
             "-c", "android.intent.category.LAUNCHER", "1"],
            timeout=15,
        )

        if result.returncode != 0:
            logger.error("Failed to launch %s: %s", package_name, result.stderr)
            return False

        # Wait for activity to appear
        return self._wait_for_ready(package_name, timeout)

    def _wait_for_ready(self, package_name: str, timeout: int) -> bool:
        """Wait until the game's main activity is in the foreground."""
        start = time.time()
        while time.time() - start < timeout:
            result = self._adb(
                ["shell", "dumpsys", "activity", "activities"],
                timeout=5,
            )
            if package_name in result.stdout:
                logger.info("Game %s is active (%.1fs)", package_name,
                            time.time() - start)
                time.sleep(3)  # Extra wait for loading screens
                return True
            time.sleep(2)

        logger.warning("Timeout waiting for %s after %ds", package_name, timeout)
        return False

    def dismiss_initial_popups(
        self,
        detect_screen_fn: Optional[Callable] = None,
        max_attempts: int = POPUP_DISMISS_ATTEMPTS,
    ) -> int:
        """
        Try to dismiss initial popups (GDPR, age gate, ads, etc.).

        Returns:
            Number of popups dismissed.
        """
        dismissed = 0
        common_close_positions = [
            (540, 1700),   # Bottom center (Accept/OK)
            (540, 1400),   # Mid-bottom
            (980, 100),    # Top-right X
            (540, 960),    # Center
        ]

        for i in range(max_attempts):
            if not self._screenshot or not self._tap:
                break

            p = self._screenshot(f"popup_check_{i}")
            if not p:
                break

            if detect_screen_fn:
                screen = detect_screen_fn(p)
                if screen not in ("popup", "ad", "overlay", "unknown"):
                    logger.info("No more popups (screen=%s)", screen)
                    break

            # Try common close positions
            pos = common_close_positions[i % len(common_close_positions)]
            self._tap(pos[0], pos[1], 2.0)
            dismissed += 1
            logger.debug("Dismissed popup attempt %d at %s", i + 1, pos)

        return dismissed

    def is_running(self, package_name: str) -> bool:
        """Check if the package is currently in the foreground."""
        result = self._adb(
            ["shell", "dumpsys", "activity", "activities"],
            timeout=5,
        )
        return package_name in result.stdout

    def get_device_resolution(self) -> Tuple[int, int]:
        """Get the device screen resolution."""
        result = self._adb(["shell", "wm", "size"], timeout=5)
        # Output: "Physical size: 1080x1920"
        for line in result.stdout.strip().split("\n"):
            if "size" in line.lower():
                parts = line.split(":")[-1].strip().split("x")
                if len(parts) == 2:
                    try:
                        return int(parts[0]), int(parts[1])
                    except ValueError:
                        pass
        return 1080, 1920  # Default
