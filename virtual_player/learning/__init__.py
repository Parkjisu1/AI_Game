"""
Learning Package -- Behavior Pattern Learning System
=====================================================
Records user demonstrations, extracts behavior patterns (not coordinates),
and replays them adaptively during autonomous play.

Three categories of learned patterns:
- quest: Quest completion flows (each quest has different steps)
- popup: Popup/reward handling (dismiss, collect, confirm)
- upgrade: Equipment/skill/character enhancement flows
"""

from .action_pattern import ActionStep, ActionPattern, PatternDB
from .pattern_recorder import PatternRecorder
from .pattern_executor import PatternExecutor
from .hierarchical_executor import HierarchicalPatternExecutor

__all__ = [
    "ActionStep",
    "ActionPattern",
    "PatternDB",
    "PatternRecorder",
    "PatternExecutor",
    "HierarchicalPatternExecutor",
]
