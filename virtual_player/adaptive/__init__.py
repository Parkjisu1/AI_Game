"""
Adaptive Planning Layer
========================
Layer 3: Wraps Goal Reasoning with failure memory, loop detection,
and spatial awareness to prevent the agent from getting stuck.
"""

from .failure_memory import FailureMemory, FailureRecord
from .loop_detector import LoopDetector, LoopDetection, LoopType
from .spatial_memory import SpatialMemory, ZoneInfo
from .plan_adapter import PlanAdapter

__all__ = [
    "FailureMemory",
    "FailureRecord",
    "LoopDetector",
    "LoopDetection",
    "LoopType",
    "SpatialMemory",
    "ZoneInfo",
    "PlanAdapter",
]
