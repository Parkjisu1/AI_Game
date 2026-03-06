"""
InputStrategy -- Pluggable ADB Input Abstraction
=================================================
Supports multiple tap methods per game profile:
  - input_tap: standard `adb shell input tap` (default)
  - monkey: `adb shell monkey` random touch (for games blocking input tap)
  - sendevent: low-level kernel touch events (for games blocking both)
  - auto: starts with input_tap, tries sendevent after failures, then monkey
"""

import logging
import re
import subprocess
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class InputStrategy:
    """Delegates tap commands to the appropriate ADB input method."""

    AUTO_FAIL_THRESHOLD = 5  # switch method after N ineffective taps

    def __init__(
        self,
        adb_fn: Callable[..., Optional[subprocess.CompletedProcess]],
        package_name: str,
        method: str = "input_tap",
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        """
        Args:
            adb_fn: Callable that runs an ADB command, e.g. orchestrator._adb.
            package_name: Android package for monkey --pct-touch targeting.
            method: One of "input_tap", "monkey", "sendevent", "auto".
            screen_width: Device screen width in pixels (for sendevent coord mapping).
            screen_height: Device screen height in pixels (for sendevent coord mapping).
        """
        self._adb = adb_fn
        self._package = package_name
        self._method = method.lower()
        self._fail_count = 0
        self._active_method = "input_tap" if self._method == "auto" else self._method

        # sendevent device info
        self._touch_device: Optional[str] = None
        self._touch_max_x: int = 32767
        self._touch_max_y: int = 32767
        self._screen_width: int = screen_width
        self._screen_height: int = screen_height

    @property
    def active_method(self) -> str:
        return self._active_method

    def tap(self, x: int, y: int, wait: float = 1.0) -> None:
        """Execute a tap using the active method."""
        if self._active_method == "monkey":
            self._monkey_tap(wait)
        elif self._active_method == "sendevent":
            self._sendevent_tap(x, y)
            time.sleep(wait)
        else:
            self._input_tap(x, y, wait)

    def report_tap_ineffective(self) -> None:
        """Call when a tap had no visible effect (screen unchanged).

        In 'auto' mode, accumulates failures and progresses through the
        fallback chain: input_tap -> sendevent -> monkey.
        """
        if self._method != "auto":
            return
        self._fail_count += 1
        if self._fail_count >= self.AUTO_FAIL_THRESHOLD:
            if self._active_method == "input_tap":
                logger.info(
                    "InputStrategy: switching to sendevent after %d ineffective taps",
                    self._fail_count,
                )
                print(f"[Input] Switching to sendevent after {self._fail_count} ineffective taps")
                self._active_method = "sendevent"
                self._fail_count = 0
            elif self._active_method == "sendevent":
                logger.info(
                    "InputStrategy: switching to monkey after %d ineffective sendevent taps",
                    self._fail_count,
                )
                print(f"[Input] Switching to monkey after {self._fail_count} ineffective sendevent taps")
                self._active_method = "monkey"
                self._fail_count = 0

    def report_tap_effective(self) -> None:
        """Call when a tap produced a visible change -- resets failure counter."""
        self._fail_count = 0

    # ------------------------------------------------------------------
    # Private: tap implementations
    # ------------------------------------------------------------------

    def _input_tap(self, x: int, y: int, wait: float) -> None:
        self._adb(["shell", "input", "tap", str(x), str(y)])
        time.sleep(wait)

    def _monkey_tap(self, wait: float) -> None:
        # Send multiple random touches to increase chance of hitting buttons
        self._adb([
            "shell", "monkey",
            "-p", self._package,
            "--pct-touch", "100",
            "--throttle", "200",
            "5",
        ])
        time.sleep(wait)

    def _sendevent_tap(self, x: int, y: int) -> None:
        """Tap using sendevent (works when input tap is blocked)."""
        if not self._touch_device:
            self._touch_device = self._detect_touch_device()
        if not self._touch_device:
            raise RuntimeError("No touch device found for sendevent")

        # Convert screen coords to touch device coords
        touch_x = int(x * self._touch_max_x / self._screen_width)
        touch_y = int(y * self._touch_max_y / self._screen_height)

        dev = self._touch_device
        cmds = [
            f"sendevent {dev} 3 57 0",           # ABS_MT_TRACKING_ID = 0
            f"sendevent {dev} 3 53 {touch_x}",   # ABS_MT_POSITION_X
            f"sendevent {dev} 3 54 {touch_y}",   # ABS_MT_POSITION_Y
            f"sendevent {dev} 1 330 1",           # BTN_TOUCH DOWN
            f"sendevent {dev} 0 0 0",             # SYN_REPORT
            f"sendevent {dev} 1 330 0",           # BTN_TOUCH UP
            f"sendevent {dev} 3 57 -1",           # ABS_MT_TRACKING_ID = -1
            f"sendevent {dev} 0 0 0",             # SYN_REPORT
        ]
        # Execute all in one shell command for atomicity
        cmd = " && ".join(cmds)
        self._adb(f'shell "{cmd}"')

    # ------------------------------------------------------------------
    # Private: device detection & calibration
    # ------------------------------------------------------------------

    def _detect_touch_device(self) -> Optional[str]:
        """Detect touch device path using getevent -p."""
        try:
            result = self._adb("shell getevent -p", timeout=5)
            # _adb may return CompletedProcess or raw string depending on caller
            if hasattr(result, "stdout"):
                output = result.stdout or ""
            else:
                output = str(result) if result else ""

            current_device = None
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("add device"):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        current_device = parts[1].strip()
                elif "ABS_MT_POSITION_X" in line and current_device:
                    # Parse max values while we have the full output
                    self._parse_touch_range(output)
                    return current_device
            return None
        except Exception as exc:
            logger.warning("InputStrategy: touch device detection failed: %s", exc)
            return None

    def _parse_touch_range(self, getevent_output: str) -> None:
        """Parse max X/Y values from getevent -p output.

        Example line:
            ABS_MT_POSITION_X : value 0, min 0, max 32767, fuzz 0, flat 0, resolution 0
        """
        for line in getevent_output.splitlines():
            if "ABS_MT_POSITION_X" in line:
                match = re.search(r'max\s+(\d+)', line)
                if match:
                    self._touch_max_x = int(match.group(1))
                    logger.debug("InputStrategy: touch_max_x=%d", self._touch_max_x)
            elif "ABS_MT_POSITION_Y" in line:
                match = re.search(r'max\s+(\d+)', line)
                if match:
                    self._touch_max_y = int(match.group(1))
                    logger.debug("InputStrategy: touch_max_y=%d", self._touch_max_y)
