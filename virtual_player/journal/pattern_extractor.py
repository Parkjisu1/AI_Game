"""
PatternExtractor -- Extract Reusable Patterns from Sessions
=============================================================
Analyzes session data to identify navigation shortcuts, failure patterns,
and timing patterns that can be reused.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class NavigationShortcut:
    """A discovered shortcut between two screens."""
    from_screen: str
    to_screen: str
    steps: List[Dict[str, Any]]
    success_rate: float = 1.0
    usage_count: int = 1


@dataclass
class FailurePattern:
    """A recurring failure pattern to avoid."""
    screen_type: str
    action: str
    description: str
    frequency: int = 1


@dataclass
class TimingPattern:
    """A timing-related pattern (e.g., loading delays, ad durations)."""
    context: str
    avg_duration: float  # seconds
    samples: int = 1


class PatternExtractor:
    """Extracts reusable patterns from session data."""

    def __init__(self):
        self.nav_shortcuts: List[NavigationShortcut] = []
        self.failure_patterns: List[FailurePattern] = []
        self.timing_patterns: List[TimingPattern] = []

    def analyze_session(self, session_data: Dict[str, Any]) -> Dict[str, int]:
        """
        Analyze a session and extract patterns.

        Args:
            session_data: Session journal data dict.

        Returns:
            {"shortcuts": N, "failures": N, "timings": N} counts of new patterns.
        """
        counts = {"shortcuts": 0, "failures": 0, "timings": 0}

        # Extract navigation shortcuts
        discovery = session_data.get("discovery_data", {})
        transitions = discovery.get("transitions", [])
        for t in transitions:
            if t.get("success_count", 0) >= 3:
                shortcut = NavigationShortcut(
                    from_screen=t["from_screen"],
                    to_screen=t["to_screen"],
                    steps=t.get("via", []),
                    success_rate=1.0,
                    usage_count=t.get("success_count", 1),
                )
                if not self._has_shortcut(shortcut):
                    self.nav_shortcuts.append(shortcut)
                    counts["shortcuts"] += 1

        # Extract failure patterns
        failed_taps = discovery.get("failed_taps", [])
        for f in failed_taps:
            if f.get("fail_count", 0) >= 5:
                pattern = FailurePattern(
                    screen_type=f["screen_type"],
                    action=f"tap({f['x']},{f['y']})",
                    description=f"Dead zone at ({f['x']},{f['y']}) on {f['screen_type']}",
                    frequency=f["fail_count"],
                )
                self.failure_patterns.append(pattern)
                counts["failures"] += 1

        # Extract timing patterns
        phases = session_data.get("phase_results", {})
        for phase_name, result in phases.items():
            duration = result.get("duration")
            if duration:
                tp = TimingPattern(
                    context=phase_name,
                    avg_duration=duration,
                    samples=1,
                )
                self._merge_timing(tp)
                counts["timings"] += 1

        return counts

    def _has_shortcut(self, shortcut: NavigationShortcut) -> bool:
        """Check if an equivalent shortcut already exists."""
        return any(
            s.from_screen == shortcut.from_screen and
            s.to_screen == shortcut.to_screen
            for s in self.nav_shortcuts
        )

    def _merge_timing(self, new_tp: TimingPattern) -> None:
        """Merge a new timing pattern with existing ones."""
        for tp in self.timing_patterns:
            if tp.context == new_tp.context:
                # Running average
                total = tp.avg_duration * tp.samples + new_tp.avg_duration
                tp.samples += 1
                tp.avg_duration = total / tp.samples
                return
        self.timing_patterns.append(new_tp)

    def to_dict(self) -> Dict[str, List]:
        """Export all patterns as a dict."""
        return {
            "nav_shortcuts": [
                {
                    "from": s.from_screen, "to": s.to_screen,
                    "steps": s.steps, "success_rate": s.success_rate,
                    "usage_count": s.usage_count,
                }
                for s in self.nav_shortcuts
            ],
            "failure_patterns": [
                {
                    "screen": f.screen_type, "action": f.action,
                    "description": f.description, "frequency": f.frequency,
                }
                for f in self.failure_patterns
            ],
            "timing_patterns": [
                {
                    "context": t.context, "avg_duration": t.avg_duration,
                    "samples": t.samples,
                }
                for t in self.timing_patterns
            ],
        }
