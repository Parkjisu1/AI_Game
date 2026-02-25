"""
ADB Control Module
===================
BlueStacks/Android ADB control + Claude Vision wrapper.
C10+ core.py에서 게임 제어에 필요한 함수만 추출.
"""

from .commands import (
    ADBConfig,
    adb_cfg,
    log,
    adb_run,
    adb_check_device,
    get_device_resolution,
    reset_resolution_cache,
    take_screenshot,
    tap,
    swipe,
    press_back,
    force_stop,
    launch_game,
    is_game_running,
    claude_vision_classify,
    claude_vision_annotate,
)

__all__ = [
    "ADBConfig",
    "adb_cfg",
    "log",
    "adb_run",
    "adb_check_device",
    "get_device_resolution",
    "reset_resolution_cache",
    "take_screenshot",
    "tap",
    "swipe",
    "press_back",
    "force_stop",
    "launch_game",
    "is_game_running",
    "claude_vision_classify",
    "claude_vision_annotate",
]
