"""
Failure Memory -- Failed Action Tracking
=========================================
Persistent memory of failed actions to avoid repeating mistakes.
Records failures per (screen_type, action_name, coords) tuple and
expires stale entries after EXPIRY_HOURS.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..adb import log


@dataclass
class FailureRecord:
    screen_type: str
    action_name: str
    coords: Tuple[int, int]       # approximate tap location
    failure_type: str              # "no_transition", "wrong_screen", "timeout"
    count: int = 0
    last_failed: float = 0.0      # unix timestamp


class FailureMemory:
    """Persistent memory of failed actions to avoid repeating mistakes."""

    COORD_TOLERANCE = 40    # pixels -- treat as same location
    EXPIRY_HOURS = 24       # forget after 24 hours
    MIN_FAILURES = 2        # mark as known-bad after 2 failures

    def __init__(self, cache_path: Optional[Path] = None):
        self._records: List[FailureRecord] = []
        self._cache_path = cache_path
        if cache_path and cache_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_failure(
        self,
        screen_type: str,
        action_name: str,
        coords: Tuple[int, int],
        failure_type: str = "no_transition",
    ) -> None:
        """Record a failed action attempt."""
        existing = self._find_record(screen_type, action_name, coords)
        if existing:
            existing.count += 1
            existing.last_failed = time.time()
        else:
            self._records.append(
                FailureRecord(
                    screen_type=screen_type,
                    action_name=action_name,
                    coords=coords,
                    failure_type=failure_type,
                    count=1,
                    last_failed=time.time(),
                )
            )
        log(
            f"  [FailureMemory] Recorded failure: {action_name} on {screen_type} "
            f"at {coords} ({failure_type})"
        )
        self._save()

    def record_success(
        self,
        screen_type: str,
        action_name: str,
        coords: Tuple[int, int],
    ) -> None:
        """Record success -- reduce failure count, remove if zeroed."""
        existing = self._find_record(screen_type, action_name, coords)
        if existing:
            existing.count = max(0, existing.count - 1)
            if existing.count == 0:
                self._records.remove(existing)
            self._save()

    def is_known_failure(
        self,
        screen_type: str,
        action_name: str,
        coords: Tuple[int, int],
    ) -> bool:
        """Return True if this action has failed >= MIN_FAILURES times within EXPIRY window."""
        self._cleanup_expired()
        rec = self._find_record(screen_type, action_name, coords)
        return rec is not None and rec.count >= self.MIN_FAILURES

    def get_failed_coords(self, screen_type: str) -> List[Tuple[int, int]]:
        """Return all known-bad coordinates for a given screen type."""
        self._cleanup_expired()
        return [
            r.coords
            for r in self._records
            if r.screen_type == screen_type and r.count >= self.MIN_FAILURES
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_record(
        self,
        screen_type: str,
        action_name: str,
        coords: Tuple[int, int],
    ) -> Optional[FailureRecord]:
        for r in self._records:
            if (
                r.screen_type == screen_type
                and r.action_name == action_name
                and abs(r.coords[0] - coords[0]) <= self.COORD_TOLERANCE
                and abs(r.coords[1] - coords[1]) <= self.COORD_TOLERANCE
            ):
                return r
        return None

    def _cleanup_expired(self) -> None:
        cutoff = time.time() - (self.EXPIRY_HOURS * 3600)
        before = len(self._records)
        self._records = [r for r in self._records if r.last_failed > cutoff]
        if len(self._records) < before:
            self._save()

    def _save(self) -> None:
        if not self._cache_path:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "screen_type": r.screen_type,
                "action_name": r.action_name,
                "coords": list(r.coords),
                "failure_type": r.failure_type,
                "count": r.count,
                "last_failed": r.last_failed,
            }
            for r in self._records
        ]
        self._cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._records = [
                FailureRecord(
                    screen_type=d["screen_type"],
                    action_name=d["action_name"],
                    coords=tuple(d["coords"]),
                    failure_type=d["failure_type"],
                    count=d["count"],
                    last_failed=d["last_failed"],
                )
                for d in data
            ]
        except Exception as e:
            log(f"  [FailureMemory] Failed to load cache: {e}")
            self._records = []
