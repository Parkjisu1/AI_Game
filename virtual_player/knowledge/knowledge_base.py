"""
KnowledgeBase -- Persistent Cross-Game Knowledge Store
======================================================
Stores learning results per game. Enables knowledge transfer between games.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Persistent game knowledge store across sessions."""

    def __init__(self, db_path: Optional[Path] = None):
        """
        Args:
            db_path: Path to knowledge.json. None = in-memory only.
        """
        self.db_path = Path(db_path) if db_path else None
        self.games: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.db_path or not self.db_path.exists():
            return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.games = data.get("games", {})
        except Exception as e:
            logger.warning("Failed to load KnowledgeBase: %s", e)

    def save(self) -> None:
        if not self.db_path:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"games": self.games, "updated": datetime.now().isoformat()}
        tmp = self.db_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(self.db_path)
        except OSError:
            if self.db_path.exists():
                self.db_path.unlink()
            tmp.rename(self.db_path)

    def register_game(
        self,
        package_name: str,
        genre: str,
        game_name: str = "",
    ) -> None:
        """Register a new game entry."""
        if package_name not in self.games:
            self.games[package_name] = {
                "game_name": game_name or package_name,
                "genre": genre,
                "first_seen": datetime.now().isoformat(),
                "sessions": 0,
                "screen_types": {},
                "nav_patterns": [],
                "parameters": {},
                "learned_actions": [],
            }
        else:
            if genre and genre != "unknown":
                self.games[package_name]["genre"] = genre

    def record_session(
        self,
        package_name: str,
        session_data: Dict[str, Any],
    ) -> None:
        """Record session results for a game."""
        if package_name not in self.games:
            self.register_game(package_name, "unknown")

        game = self.games[package_name]
        game["sessions"] += 1
        game["last_session"] = datetime.now().isoformat()

        # Merge screen types
        for st, desc in session_data.get("screen_types", {}).items():
            game["screen_types"][st] = desc

        # Merge nav patterns
        for pattern in session_data.get("nav_patterns", []):
            if pattern not in game["nav_patterns"]:
                game["nav_patterns"].append(pattern)

        # Merge parameters
        for pid, val in session_data.get("parameters", {}).items():
            game["parameters"][pid] = val

        # Merge learned actions
        for action in session_data.get("learned_actions", []):
            if action not in game["learned_actions"]:
                game["learned_actions"].append(action)

    def get_game(self, package_name: str) -> Optional[Dict]:
        """Get knowledge for a specific game."""
        return self.games.get(package_name)

    def get_games_by_genre(self, genre: str) -> List[str]:
        """Get all package names for a genre."""
        return [
            pkg for pkg, data in self.games.items()
            if data.get("genre", "") == genre
        ]

    def has_game(self, package_name: str) -> bool:
        return package_name in self.games
