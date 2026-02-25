"""
ADB Game Adapter
==================
GameAdapter implementation for Android games via ADB (BlueStacks).
connect = launch game, get_game_state = take screenshot, send_input = tap/swipe.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..brain.base import TouchInput, ActionType
from ..adb import (
    log, adb_check_device, take_screenshot, tap, swipe, press_back,
    force_stop, launch_game, is_game_running, get_device_resolution,
)
from .base import GameAdapter


class ADBAdapter(GameAdapter):
    """Game adapter for Android games controlled via ADB.

    get_game_state() returns a screenshot path (Path object).
    The Brain is responsible for interpreting the screenshot.
    """

    def __init__(
        self,
        package_name: str,
        user_agent: str = "",
        device_profile: Optional[Dict[str, Any]] = None,
        temp_dir: Optional[Path] = None,
    ):
        super().__init__(user_agent=user_agent, device_profile=device_profile)
        self.package_name = package_name
        self._temp_dir = temp_dir or Path(__file__).parent.parent / "data" / "temp"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._screenshot_counter = 0

    async def connect(self) -> None:
        """Connect to device and launch game if not running."""
        if not adb_check_device():
            raise ConnectionError("ADB device not found. Is BlueStacks running?")

        if not is_game_running(self.package_name):
            log(f"  [ADB] Launching {self.package_name}...")
            await asyncio.to_thread(launch_game, self.package_name, 8)
        else:
            log(f"  [ADB] Game already running: {self.package_name}")

        self._connected = True
        w, h = get_device_resolution()
        log(f"  [ADB] Connected. Resolution: {w}x{h}")

    async def get_game_state(self) -> Path:
        """Take a screenshot and return its path.

        The VisionBrain will classify this screenshot to determine game state.
        """
        self._screenshot_counter += 1
        shot_path = self._temp_dir / f"state_{self._screenshot_counter:06d}.png"
        success = await asyncio.to_thread(take_screenshot, shot_path)
        if not success:
            raise RuntimeError("Failed to take screenshot")
        return shot_path

    async def send_input(self, inputs: List[TouchInput]) -> None:
        """Execute touch inputs via ADB."""
        for inp in inputs:
            if inp.action_type == ActionType.TAP:
                await asyncio.to_thread(
                    tap, int(inp.x), int(inp.y),
                    inp.duration if inp.duration > 0 else 0.3
                )
            elif inp.action_type == ActionType.SWIPE:
                dur_ms = int(inp.duration * 1000) if inp.duration > 0 else 300
                await asyncio.to_thread(
                    swipe,
                    int(inp.x), int(inp.y),
                    int(inp.end_x), int(inp.end_y),
                    dur_ms, 0.3,
                )
            elif inp.action_type == ActionType.KEY_PRESS:
                if inp.key == "back":
                    await asyncio.to_thread(press_back, 0.3)
            elif inp.action_type == ActionType.WAIT:
                await asyncio.sleep(inp.duration if inp.duration > 0 else 1.0)

    async def disconnect(self) -> None:
        """Disconnect (leave game running)."""
        self._connected = False
        log(f"  [ADB] Disconnected (game left running)")

    async def restart_game(self) -> None:
        """Force-stop and relaunch the game."""
        log(f"  [ADB] Restarting {self.package_name}...")
        await asyncio.to_thread(force_stop, self.package_name)
        await asyncio.to_thread(launch_game, self.package_name, 8)
