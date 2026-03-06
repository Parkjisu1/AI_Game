"""Value estimation for action outcomes -- tracks resource rates per action."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional
import time

@dataclass
class ActionOutcome:
    action_name: str
    gold_delta: float = 0.0
    xp_delta: float = 0.0
    hp_delta: float = 0.0
    duration_s: float = 1.0
    timestamp: float = 0.0

class ValueEstimator:
    """Tracks action outcomes and estimates resource generation rates."""

    MAX_HISTORY = 20  # Rolling window per action

    def __init__(self):
        self._history: Dict[str, deque] = {}  # action_name -> deque of ActionOutcome
        self._global_rates: Dict[str, float] = {}  # resource -> rate per second

    def record_outcome(self, action_name: str, before_state: dict, after_state: dict, duration_s: float):
        """Record outcome of an action by comparing before/after states."""
        if duration_s <= 0:
            duration_s = 1.0

        outcome = ActionOutcome(
            action_name=action_name,
            gold_delta=_safe_delta(after_state, before_state, 'gold'),
            xp_delta=_safe_delta(after_state, before_state, 'xp'),
            hp_delta=_safe_delta(after_state, before_state, 'hp_pct'),
            duration_s=duration_s,
            timestamp=time.time(),
        )

        if action_name not in self._history:
            self._history[action_name] = deque(maxlen=self.MAX_HISTORY)
        self._history[action_name].append(outcome)
        self._update_global_rates()

    def estimate_value(self, action_name: str) -> float:
        """Estimate gold-equivalent value per second for an action."""
        history = self._history.get(action_name)
        if not history:
            return 0.0

        total_gold = sum(o.gold_delta for o in history)
        total_xp = sum(o.xp_delta for o in history)
        total_time = sum(o.duration_s for o in history)

        if total_time <= 0:
            return 0.0

        # Gold-equivalent: gold + xp * 0.5 (xp has indirect value)
        gold_equiv = total_gold + total_xp * 0.5
        return gold_equiv / total_time

    def get_resource_rates(self) -> Dict[str, float]:
        """Get per-resource generation rates (units/second) across all actions."""
        return dict(self._global_rates)

    def get_best_action(self) -> Optional[str]:
        """Return action name with highest value/second."""
        if not self._history:
            return None
        return max(self._history.keys(), key=lambda a: self.estimate_value(a))

    def _update_global_rates(self):
        """Recalculate global resource rates from all history."""
        totals = {'gold_rate': 0.0, 'xp_rate': 0.0}
        total_time = 0.0

        for history in self._history.values():
            for o in history:
                totals['gold_rate'] += o.gold_delta
                totals['xp_rate'] += o.xp_delta
                total_time += o.duration_s

        if total_time > 0:
            self._global_rates = {k: v / total_time for k, v in totals.items()}
        else:
            self._global_rates = {}


def _safe_delta(after: dict, before: dict, key: str) -> float:
    """Safely compute after[key] - before[key]."""
    a = after.get(key, 0) or 0
    b = before.get(key, 0) or 0
    try:
        return float(a) - float(b)
    except (TypeError, ValueError):
        return 0.0
