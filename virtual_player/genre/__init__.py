"""
Genre Abstraction Layer
========================
Provides genre-specific configurations (concepts, ROIs, goals, actions, interrupts)
to bootstrap the virtual player for a new game without manual tuning.

Supported genres: RPG, Idle, Merge, SLG
"""

from .game_profile import GameProfile, get_schema_for_genre
from .idle_schema import IdleSchema
from .merge_schema import MergeSchema
from .rpg_schema import RPGSchema
from .schema import GenreConcept, GenreSchema
from .setup_wizard import SetupWizard
from .slg_schema import SLGSchema

__all__ = [
    # Abstract base
    "GenreSchema",
    "GenreConcept",
    # Concrete schemas
    "RPGSchema",
    "IdleSchema",
    "MergeSchema",
    "SLGSchema",
    # Profile + factory
    "GameProfile",
    "get_schema_for_genre",
    # Wizard
    "SetupWizard",
]
