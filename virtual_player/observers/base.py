"""
ObserverBase -- Abstract Base for Parameter Observers
======================================================
Each observer specializes in a domain (gameplay, ux, numeric, economy, etc.)
and records parameter observations with confidence scores.

Extracted from carmatch_tester.py and made game-agnostic.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Type alias for screenshot capture function
ScreenCaptureFn = Callable[[str], Optional[Path]]


class ObserverBase(ABC):
    """Abstract base class for parameter observers."""

    def __init__(
        self,
        observer_id: int,
        name: str,
        domain: str,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List[Dict[str, Any]]],
    ):
        """
        Args:
            observer_id: Unique observer number (1-N).
            name: Human-readable observer name.
            domain: Primary domain expertise (gameplay, ux, numeric, etc.).
            capture_fn: (label) -> Path. Screenshot capture function.
            observations: Shared dict for recording observations. Keys are param IDs.
        """
        self.id = observer_id
        self.name = name
        self.domain = domain
        self._capture = capture_fn
        self.observations = observations

    def observe(
        self,
        param_id: str,
        value: Any,
        confidence: float = 0.8,
        notes: str = "",
    ) -> None:
        """
        Record a parameter observation.

        Args:
            param_id: Parameter identifier (e.g., "CM01", "board_width").
            value: Observed value (any type).
            confidence: Confidence score 0.0-1.0.
            notes: Explanation text.
        """
        if param_id not in self.observations:
            self.observations[param_id] = []

        self.observations[param_id].append({
            "value": value,
            "confidence": min(1.0, max(0.0, confidence)),
            "observer": self.id,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        })
        logger.debug(
            "[Observer %d/%s] %s = %s (conf=%.2f)",
            self.id, self.name, param_id, value, confidence,
        )

    def screenshot(self, label: str = "") -> Optional[Path]:
        """Capture a screenshot with optional label."""
        full_label = f"obs{self.id}_{label}" if label else f"obs{self.id}"
        return self._capture(full_label)

    @abstractmethod
    def run(self) -> None:
        """Execute observation logic. Must be implemented by subclasses."""
        ...

    def __repr__(self) -> str:
        return f"<Observer {self.id}: {self.name} [{self.domain}]>"
