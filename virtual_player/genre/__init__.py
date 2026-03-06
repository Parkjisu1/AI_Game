"""
Genre Abstraction Layer
========================
Provides genre-specific configurations (concepts, ROIs, goals, actions, interrupts)
to bootstrap the virtual player for a new game without manual tuning.

Supported genres: RPG, Idle, Merge, SLG, Puzzle, Tycoon, Simulation, Casual
"""

from .casual_schema import CasualSchema
from .game_profile import GameProfile, get_schema_for_genre
from .idle_schema import IdleSchema
from .merge_schema import MergeSchema
from .puzzle_schema import PuzzleSchema
from .rpg_schema import RPGSchema
from .schema import GenreConcept, GenreSchema
from .setup_wizard import SetupWizard
from .simulation_schema import SimulationSchema
from .slg_schema import SLGSchema
from .tycoon_schema import TycoonSchema

__all__ = [
    # Abstract base
    "GenreSchema",
    "GenreConcept",
    # Concrete schemas
    "RPGSchema",
    "IdleSchema",
    "MergeSchema",
    "SLGSchema",
    "PuzzleSchema",
    "TycoonSchema",
    "SimulationSchema",
    "CasualSchema",
    # Profile + factory
    "GameProfile",
    "get_schema_for_genre",
    # Wizard
    "SetupWizard",
]
