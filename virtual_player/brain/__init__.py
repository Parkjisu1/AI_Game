"""
Brain module - 게임별 AI 두뇌.
"""

from pathlib import Path
from typing import Dict, Optional
from .base import GameBrain, GameAction, GameState, TouchInput, ActionType


# ============================================================
# Brain factory
# ============================================================

_BRAIN_REGISTRY: dict[str, type[GameBrain]] = {}


def register_brain(game_id: str, brain_cls: type[GameBrain]) -> None:
    """게임 ID에 Brain 클래스를 등록."""
    _BRAIN_REGISTRY[game_id] = brain_cls


def get_brain(game_id: str, skill_level: float = 0.5) -> GameBrain:
    """게임 ID로 Brain 인스턴스 생성."""
    if game_id not in _BRAIN_REGISTRY:
        available = ", ".join(_BRAIN_REGISTRY.keys()) or "(none)"
        raise ValueError(
            f"Unknown game '{game_id}'. Available: {available}"
        )
    return _BRAIN_REGISTRY[game_id](skill_level=skill_level)


def create_vision_brain(
    screen_types: Dict[str, str],
    game_package: str,
    cache_dir: Path,
    skill_level: float = 0.5,
    nav_graph_path: Optional[Path] = None,
    screen_equivalences: Optional[Dict[str, str]] = None,
    state_reader=None,
    plan_adapter=None,
) -> "GameBrain":
    """Create a VisionBrain for ADB-based Android game playing.

    Optional intelligent layers:
      state_reader: perception.StateReader for HP/gold/stats extraction
      plan_adapter: adaptive.PlanAdapter for GOAP + utility AI + failure memory
    """
    from .vision_brain import VisionBrain
    return VisionBrain(
        screen_types=screen_types,
        game_package=game_package,
        cache_dir=cache_dir,
        skill_level=skill_level,
        nav_graph_path=nav_graph_path,
        screen_equivalences=screen_equivalences,
        state_reader=state_reader,
        plan_adapter=plan_adapter,
    )
