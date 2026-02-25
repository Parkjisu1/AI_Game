"""
SetupWizard — New Game Profile Onboarding
==========================================
Creates a GameProfile for a new game, seeding it with genre defaults
from the appropriate GenreSchema. Saves a profile.yaml ready for use.
"""

from pathlib import Path
from typing import Dict

from ..adb import log
from .game_profile import GameProfile, get_schema_for_genre


class SetupWizard:
    """Interactive (or programmatic) setup for a new game."""

    def __init__(self, games_dir: Path):
        self._games_dir = games_dir

    def setup(self, game_id: str, package_name: str, genre: str) -> GameProfile:
        """Create a new game profile with genre defaults and save to disk.

        Args:
            game_id:      Unique identifier (e.g. "my_rpg_game")
            package_name: Android package name (e.g. "com.example.mygame")
            genre:        Genre key ("rpg", "idle", "merge", "slg")

        Returns:
            Populated and saved GameProfile.
        """
        schema = get_schema_for_genre(genre)
        if schema is None:
            log(f"  [SetupWizard] Unknown genre '{genre}', using rpg defaults")
            from .rpg_schema import RPGSchema
            schema = RPGSchema()

        profile = GameProfile(
            game_id=game_id,
            game_name=game_id.replace("_", " ").title(),
            package_name=package_name,
            genre=genre,
        )

        # Apply default screen ROIs from the genre schema
        for screen_type, roi in schema.get_default_screen_rois().items():
            screen_rois: Dict[str, dict] = {}
            for name, cfg in roi.gauge_regions.items():
                screen_rois[name] = {**cfg, "type": "gauge", "gauge_name": name}
            for name, cfg in roi.ocr_regions.items():
                screen_rois[name] = {**cfg, "type": "ocr"}
            if screen_rois:
                profile.screen_rois[screen_type] = screen_rois

        profile_path = self._games_dir / game_id / "profile.yaml"
        profile.save(profile_path)
        log(f"  [SetupWizard] Profile saved: {profile_path}")

        return profile

    def auto_detect_genre(self, screen_types: Dict[str, str]) -> str:
        """Guess the genre based on observed screen type names.

        Args:
            screen_types: Mapping of screen_type_key -> description (from perception).

        Returns:
            Best-guess genre key string.
        """
        names = set(screen_types.keys())

        rpg_screens = {"battle", "menu_character", "menu_skill", "equipment_detail", "summon"}
        if len(names & rpg_screens) >= 2:
            return "rpg"

        idle_screens = {"idle_screen", "prestige", "offline_reward"}
        if len(names & idle_screens) >= 1:
            return "idle"

        merge_screens = {"game_board", "merge", "orders"}
        if len(names & merge_screens) >= 1:
            return "merge"

        slg_screens = {"world_map", "barracks", "rally", "base_view"}
        if len(names & slg_screens) >= 1:
            return "slg"

        return "rpg"
