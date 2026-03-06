"""
Discovery Package
==================
UI element discovery, dead-zone tracking, and safety mechanisms.
Extracted from smart_player.py for reuse across games.
"""

from .discovery_db import DiscoveryDB
from .exploration_engine import ExplorationEngine
from .safety_guard import SafetyGuard

__all__ = ["DiscoveryDB", "ExplorationEngine", "SafetyGuard"]
