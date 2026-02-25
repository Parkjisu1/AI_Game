"""
GenreSchema — Abstract Base for Genre-Specific Game Configurations
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
