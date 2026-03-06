"""
TransferEngine -- Cross-Game Knowledge Transfer
================================================
Applies knowledge from previously played games to new games of the same genre.
"""

import logging
from typing import Any, Dict, List, Optional

from .knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class TransferEngine:
    """Transfers knowledge from known games to new games."""

    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base

    def get_transfer_data(
        self,
        target_package: str,
        target_genre: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get transferable knowledge for a new game based on same-genre games.

        Args:
            target_package: Package name of the new game.
            target_genre: Detected genre of the new game.

        Returns:
            Dict with transferable knowledge, or None if no prior knowledge.
        """
        same_genre = self.kb.get_games_by_genre(target_genre)
        # Exclude the target itself
        sources = [pkg for pkg in same_genre if pkg != target_package]

        if not sources:
            logger.info("No prior %s games in knowledge base", target_genre)
            return None

        logger.info(
            "Found %d prior %s games for transfer: %s",
            len(sources), target_genre, sources,
        )

        transfer = {
            "source_games": sources,
            "genre": target_genre,
            "screen_types": self._merge_screen_types(sources),
            "nav_patterns": self._merge_nav_patterns(sources),
            "common_parameters": self._merge_parameters(sources),
            "learned_actions": self._merge_actions(sources),
        }

        return transfer

    def apply_transfer(
        self,
        transfer_data: Dict[str, Any],
        discovery_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply transferred knowledge to enrich DiscoveryDB data.

        Args:
            transfer_data: Output from get_transfer_data().
            discovery_data: Current DiscoveryDB.to_dict().

        Returns:
            Enriched discovery data with transferred knowledge.
        """
        if not transfer_data:
            return discovery_data

        enriched = dict(discovery_data)
        screens = enriched.get("screens", {})

        # Add expected screen types that haven't been discovered yet
        for st, desc in transfer_data.get("screen_types", {}).items():
            if st not in screens:
                screens[st] = {
                    "visit_count": 0,
                    "elements": [],
                    "tags": ["transferred"],
                }

        enriched["screens"] = screens
        enriched["_transfer_applied"] = True
        enriched["_transfer_sources"] = transfer_data.get("source_games", [])

        return enriched

    def _merge_screen_types(self, packages: List[str]) -> Dict[str, str]:
        """Merge screen types from multiple games."""
        merged = {}
        for pkg in packages:
            game = self.kb.get_game(pkg)
            if game:
                for st, desc in game.get("screen_types", {}).items():
                    if st not in merged:
                        merged[st] = desc
        return merged

    def _merge_nav_patterns(self, packages: List[str]) -> List[Dict]:
        """Merge navigation patterns from multiple games."""
        patterns = []
        seen = set()
        for pkg in packages:
            game = self.kb.get_game(pkg)
            if game:
                for pattern in game.get("nav_patterns", []):
                    key = str(pattern)
                    if key not in seen:
                        patterns.append(pattern)
                        seen.add(key)
        return patterns

    def _merge_parameters(self, packages: List[str]) -> Dict[str, Any]:
        """Merge common parameters (take most recent)."""
        merged = {}
        for pkg in packages:
            game = self.kb.get_game(pkg)
            if game:
                for pid, val in game.get("parameters", {}).items():
                    merged[pid] = val  # Last write wins
        return merged

    def _merge_actions(self, packages: List[str]) -> List[str]:
        """Merge learned actions."""
        actions = set()
        for pkg in packages:
            game = self.kb.get_game(pkg)
            if game:
                actions.update(game.get("learned_actions", []))
        return list(actions)
