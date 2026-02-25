"""
Utility Scorer — Dave Mark's Utility AI System
================================================
Evaluates goals using response curves and multiplicative scoring.
Each goal has multiple Considerations that map world state values
to 0~1 utility scores via configurable response curves.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class CurveType(str, Enum):
    LINEAR = "linear"       # y = mx + b
    INVERSE = "inverse"     # y = 1 - x (or custom)
    SIGMOID = "sigmoid"     # y = 1/(1+e^(-k*(x-mid)))
    STEP = "step"           # y = 1 if x > threshold else 0
    QUADRATIC = "quadratic" # y = x^2


@dataclass
class Consideration:
    """Maps a state value to a 0~1 utility score via response curve."""
    name: str
    input_key: str          # WorldState prop key to read
    curve_type: CurveType = CurveType.LINEAR
    weight: float = 1.0
    # Curve parameters
    m: float = 1.0          # slope (linear)
    b: float = 0.0          # offset (linear)
    k: float = 10.0         # steepness (sigmoid)
    mid: float = 0.5        # midpoint (sigmoid)
    threshold: float = 0.5  # step threshold
    clamp_min: float = 0.0
    clamp_max: float = 1.0
    invert: bool = False    # if True, score = 1 - score

    def evaluate(self, input_value: float) -> float:
        """Evaluate the response curve for the given input value."""
        if input_value is None:
            return 0.0

        if self.curve_type == CurveType.LINEAR:
            score = self.m * input_value + self.b
        elif self.curve_type == CurveType.INVERSE:
            score = 1.0 - input_value
        elif self.curve_type == CurveType.SIGMOID:
            exp_val = -self.k * (input_value - self.mid)
            exp_val = max(-500, min(500, exp_val))  # prevent overflow
            score = 1.0 / (1.0 + math.exp(exp_val))
        elif self.curve_type == CurveType.STEP:
            score = 1.0 if input_value >= self.threshold else 0.0
        elif self.curve_type == CurveType.QUADRATIC:
            score = input_value ** 2
        else:
            score = input_value

        if self.invert:
            score = 1.0 - score

        return max(self.clamp_min, min(self.clamp_max, score))


@dataclass
class GoalScorer:
    """Scores a single goal using multiple considerations (multiplicative)."""
    goal_name: str
    considerations: List[Consideration] = field(default_factory=list)

    def score(self, world_state) -> float:
        """Dave Mark's multiplicative scoring with compensation factor.

        compensation = 1 - (1/n) where n = number of considerations.
        Final = product of (score + (1-score) * compensation) for each consideration.
        """
        if not self.considerations:
            return 0.0

        n = len(self.considerations)
        compensation = 1.0 - (1.0 / n) if n > 1 else 0.0

        final = 1.0
        for c in self.considerations:
            raw_val = world_state.props.get(c.input_key, 0.0)
            if raw_val is None:
                raw_val = 0.0
            score = c.evaluate(float(raw_val))
            # Apply weight
            weighted = score * c.weight
            # Apply compensation factor
            compensated = weighted + (1.0 - weighted) * compensation
            final *= compensated

        return final


class UtilityScorer:
    """Evaluates all goals and returns priority-ranked list."""

    def __init__(self, goal_scorers: Optional[List[GoalScorer]] = None):
        self._scorers: List[GoalScorer] = goal_scorers or []

    def add_scorer(self, scorer: GoalScorer):
        self._scorers.append(scorer)

    def set_scorers(self, scorers: List[GoalScorer]):
        self._scorers = scorers

    def evaluate(self, world_state) -> List[tuple]:
        """Return list of (goal_name, score) sorted by score descending."""
        results = []
        for scorer in self._scorers:
            score = scorer.score(world_state)
            results.append((scorer.goal_name, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get_best(self, world_state) -> Optional[tuple]:
        """Return (goal_name, score) of the highest-scoring goal."""
        results = self.evaluate(world_state)
        return results[0] if results else None
