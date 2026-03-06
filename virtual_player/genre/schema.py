"""
GenreSchema -- Abstract Base for Genre-Specific Game Configurations
===================================================================
Defines the contract that each genre schema must fulfill:
concepts, screen ROIs, goals, actions, interrupts, and gauge profiles.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ..perception.region_registry import ScreenROI
    from ..perception.gauge_reader import GaugeProfile
    from ..reasoning.goap_planner import GOAPAction, GOAPGoal, WorldState
    from ..reasoning.utility_scorer import GoalScorer


@dataclass
class GenreConcept:
    """A game concept relevant to the genre (e.g., HP, gold, board)."""
    name: str                                     # "hp", "gold", "board_state"
    category: str                                 # "gauge", "resource", "stat", "special"
    description: str = ""
    default_gauge_profile: Optional[str] = None  # for gauge type
    is_required: bool = True


class GenreSchema(ABC):
    """Abstract base class for genre-specific game configurations."""

    @property
    @abstractmethod
    def genre_key(self) -> str:
        """Short identifier: 'rpg', 'idle', 'merge', 'slg'."""
        ...

    @property
    @abstractmethod
    def genre_name(self) -> str:
        """Display name: 'RPG', 'Idle', 'Merge', 'SLG'."""
        ...

    @abstractmethod
    def get_concepts(self) -> Dict[str, "GenreConcept"]:
        """Get all game concepts for this genre."""
        ...

    @abstractmethod
    def get_default_screen_rois(self) -> Dict[str, "ScreenROI"]:
        """Get default ROI definitions for common screens."""
        ...

    @abstractmethod
    def get_goal_templates(self) -> List["GoalScorer"]:
        """Get pre-configured goal scorers for this genre."""
        ...

    @abstractmethod
    def get_action_templates(self) -> List["GOAPAction"]:
        """Get pre-configured GOAP actions for this genre."""
        ...

    @abstractmethod
    def get_interrupt_rules(self) -> List[dict]:
        """Get emergency interrupt rules.

        Each dict: {name, condition: Callable[[WorldState], bool], goal_name, priority}
        """
        ...

    def get_gauge_profiles(self) -> List["GaugeProfile"]:
        """Get custom gauge color profiles for this genre. Defaults to empty (use system defaults)."""
        return []

    def get_screen_types(self) -> Dict[str, str]:
        """Get typical screen types for this genre as {key: description}."""
        return {}

    def get_exploration_hints(self) -> Dict[str, list]:
        """
        Get hints for the ExplorationEngine specific to this genre.

        Returns:
            Dict with optional keys:
            - "priority_screens": screens to explore first
            - "safe_screens": screens where exploration is always safe
            - "danger_screens": screens to avoid exploring
            - "ocr_keywords": keywords indicating important UI elements
        """
        return {}

    def get_combat_config(self) -> dict:
        """Get combat configuration for CombatController.

        Returns:
            Dict with optional keys:
            - "skill_slots": list of skill slot dicts (name, x, y, cooldown_s, priority, type)
        Defaults to empty dict (no combat controller will be created).
        """
        return {}
