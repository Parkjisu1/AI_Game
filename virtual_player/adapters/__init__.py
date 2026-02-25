"""
Adapters module - 게임 연결 어댑터.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from .base import GameAdapter


# ============================================================
# Adapter factory
# ============================================================

_ADAPTER_REGISTRY: dict[str, type[GameAdapter]] = {}


def register_adapter(game_id: str, adapter_cls: type[GameAdapter]) -> None:
    """게임 ID에 Adapter 클래스를 등록."""
    _ADAPTER_REGISTRY[game_id] = adapter_cls


def get_adapter(
    game_id: str,
    user_agent: str = "",
    device_profile: Optional[Dict[str, Any]] = None,
) -> GameAdapter:
    """게임 ID로 Adapter 인스턴스 생성."""
    if game_id not in _ADAPTER_REGISTRY:
        available = ", ".join(_ADAPTER_REGISTRY.keys()) or "(none)"
        raise ValueError(
            f"Unknown game '{game_id}'. Available: {available}"
        )
    return _ADAPTER_REGISTRY[game_id](
        user_agent=user_agent,
        device_profile=device_profile,
    )


def create_adb_adapter(
    package_name: str,
    temp_dir: Optional[Path] = None,
) -> "GameAdapter":
    """Create an ADB adapter for Android game control."""
    from .adb_adapter import ADBAdapter
    return ADBAdapter(package_name=package_name, temp_dir=temp_dir)
