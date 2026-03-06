"""
GameProfile -- Per-Game YAML Configuration
==========================================
Loads and saves game-specific settings that overlay genre defaults.
Covers gauge overrides, screen ROIs, custom goals, and custom actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import yaml

if TYPE_CHECKING:
    from .schema import GenreSchema


@dataclass
class GameProfile:
    """Per-game configuration loaded from YAML."""
    game_id: str
    game_name: str
    package_name: str
    genre: str                                            # "rpg", "idle", "merge", "slg"
    gauge_overrides: Dict[str, dict] = field(default_factory=dict)   # override HSV ranges
    screen_rois: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    custom_goals: List[dict] = field(default_factory=list)
    custom_actions: List[dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Cross-genre fields (backwards-compatible defaults)
    reasoner_genre: Optional[str] = None                  # e.g. "rpg_anv" -- overrides genre for GOAP
    fallback_positions: List[List[int]] = field(default_factory=list)  # [[x,y], ...] for stuck escape
    pixel_heuristic: Optional[Dict[str, Any]] = None      # {y_top, y_bot, rules: [{screen_type, condition}]}
    gauge_bars: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # e.g. mp: {y, x_start, x_end, ...}
    input_method: str = "input_tap"                       # "input_tap", "monkey", "auto"
    launch_activity: str = ""                             # e.g. "com.unity3d.player.UnityPlayerActivity"

    @staticmethod
    def load(path: "str | Path") -> "GameProfile":
        """Load a GameProfile from a YAML file."""
        path = Path(path) if not isinstance(path, Path) else path
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return GameProfile(
            game_id=data.get("game_id", "unknown"),
            game_name=data.get("game_name", "Unknown"),
            package_name=data.get("package_name", ""),
            genre=data.get("genre", "rpg"),
            gauge_overrides=data.get("gauge_overrides", {}),
            screen_rois=data.get("screen_rois", {}),
            custom_goals=data.get("custom_goals", []),
            custom_actions=data.get("custom_actions", []),
            metadata=data.get("metadata", {}),
            reasoner_genre=data.get("reasoner_genre"),
            fallback_positions=data.get("fallback_positions", []),
            pixel_heuristic=data.get("pixel_heuristic"),
            gauge_bars=data.get("gauge_bars", {}),
            input_method=data.get("input_method", "input_tap"),
            launch_activity=data.get("launch_activity", ""),
        )

    def save(self, path: Path) -> None:
        """Save this GameProfile to a YAML file."""
        data: Dict[str, Any] = {
            "game_id": self.game_id,
            "game_name": self.game_name,
            "package_name": self.package_name,
            "genre": self.genre,
        }
        if self.gauge_overrides:
            data["gauge_overrides"] = self.gauge_overrides
        if self.screen_rois:
            data["screen_rois"] = self.screen_rois
        if self.custom_goals:
            data["custom_goals"] = self.custom_goals
        if self.custom_actions:
            data["custom_actions"] = self.custom_actions
        if self.metadata:
            data["metadata"] = self.metadata
        if self.reasoner_genre:
            data["reasoner_genre"] = self.reasoner_genre
        if self.fallback_positions:
            data["fallback_positions"] = self.fallback_positions
        if self.pixel_heuristic:
            data["pixel_heuristic"] = self.pixel_heuristic
        if self.gauge_bars:
            data["gauge_bars"] = self.gauge_bars
        if self.input_method != "input_tap":
            data["input_method"] = self.input_method
        if self.launch_activity:
            data["launch_activity"] = self.launch_activity
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )


def get_schema_for_genre(genre: str) -> Optional["GenreSchema"]:
    """Return an instantiated GenreSchema for the given genre key, or None if unknown."""
    from .casual_schema import CasualSchema
    from .idle_schema import IdleSchema
    from .merge_schema import MergeSchema
    from .puzzle_schema import PuzzleSchema
    from .rpg_schema import RPGSchema
    from .simulation_schema import SimulationSchema
    from .slg_schema import SLGSchema
    from .tycoon_schema import TycoonSchema

    schemas = {
        "rpg": RPGSchema,
        "idle": IdleSchema,
        "merge": MergeSchema,
        "slg": SLGSchema,
        "puzzle": PuzzleSchema,
        "tycoon": TycoonSchema,
        "simulation": SimulationSchema,
        "casual": CasualSchema,
    }
    cls = schemas.get(genre.lower())
    return cls() if cls else None
