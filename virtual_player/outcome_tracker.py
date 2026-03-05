"""
Outcome Tracker
================
Tracks action outcomes and manages BT node promotion.

Flow:
  1. record_attempt(screen, action, coords) -- before action
  2. record_result(screen_changed, new_screen) -- after action
  3. If success_count >= PROMOTE_THRESHOLD -> promote to BT node
  4. If fail_count >= DEMOTE_THRESHOLD -> demote (disable) node

Also tracks Vision AI actions for automatic BT promotion.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


PROMOTE_THRESHOLD = 3    # successes to promote vision action to BT node
DEMOTE_THRESHOLD = 3     # failures to disable a BT node
EXPIRY_HOURS = 48        # forget old records


@dataclass
class ActionRecord:
    screen_type: str
    action_name: str
    coords: Tuple[int, int]
    action_type: str = "tap"  # tap, swipe, back, wait
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0
    promoted: bool = False
    source: str = "unknown"  # "nav_graph", "vision", "discovery", "promoted"


class OutcomeTracker:
    """Tracks action outcomes for BT node promotion/demotion."""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        on_promote: Optional[Callable[[str, Dict], None]] = None,
    ):
        self._records: Dict[str, List[ActionRecord]] = {}  # screen_type -> records
        self._cache_path = cache_path
        self._on_promote = on_promote  # callback when a node should be promoted
        self._pending_action: Optional[ActionRecord] = None
        if cache_path and cache_path.exists():
            self._load()

    def record_attempt(
        self,
        screen_type: str,
        action_name: str,
        coords: Tuple[int, int],
        source: str = "bt",
    ) -> None:
        """Record that an action was attempted. Call before executing."""
        rec = self._find_or_create(screen_type, action_name, coords)
        rec.last_used = time.time()
        rec.source = source
        self._pending_action = rec

    def record_result(self, screen_changed: bool, new_screen: str = "") -> None:
        """Record the outcome of the last attempted action.

        Args:
            screen_changed: True if screen changed after action.
            new_screen: The new screen type (if changed).
        """
        if self._pending_action is None:
            return

        rec = self._pending_action
        self._pending_action = None

        if screen_changed:
            rec.success_count += 1
            logger.debug("OutcomeTracker: SUCCESS %s on %s (%d/%d)",
                         rec.action_name, rec.screen_type,
                         rec.success_count, rec.fail_count)
        else:
            rec.fail_count += 1
            logger.debug("OutcomeTracker: FAIL %s on %s (%d/%d)",
                         rec.action_name, rec.screen_type,
                         rec.success_count, rec.fail_count)

        # Check promotion
        if (not rec.promoted
                and rec.success_count >= PROMOTE_THRESHOLD
                and rec.source == "vision"):
            rec.promoted = True
            self._promote(rec)

        self._save()

    def record_vision_action(
        self,
        screen_type: str,
        description: str,
        coords: Tuple[int, int],
        action_type: str = "tap",
    ) -> None:
        """Record a vision AI action for tracking (pre-promotion)."""
        rec = self._find_or_create(screen_type, description, coords)
        rec.source = "vision"
        rec.action_type = action_type
        rec.last_used = time.time()
        self._pending_action = rec

    def is_known_failure(
        self,
        screen_type: str,
        action_name: str,
        coords: Tuple[int, int],
    ) -> bool:
        """Check if this action is a known failure (should be skipped)."""
        rec = self._find_record(screen_type, action_name, coords)
        return rec is not None and rec.fail_count >= DEMOTE_THRESHOLD

    def get_success_rate(self, screen_type: str, action_name: str) -> float:
        """Get success rate for an action (0.0 to 1.0)."""
        records = self._records.get(screen_type, [])
        for rec in records:
            if rec.action_name == action_name:
                total = rec.success_count + rec.fail_count
                return rec.success_count / total if total > 0 else 0.5
        return 0.5  # unknown = neutral

    def get_promoted_actions(self) -> Dict[str, List[Dict]]:
        """Get all promoted actions grouped by screen type."""
        result: Dict[str, List[Dict]] = {}
        for screen_type, records in self._records.items():
            for rec in records:
                if rec.promoted:
                    if screen_type not in result:
                        result[screen_type] = []
                    result[screen_type].append({
                        "name": rec.action_name,
                        "x": rec.coords[0],
                        "y": rec.coords[1],
                        "action_type": rec.action_type,
                        "success_count": rec.success_count,
                    })
        return result

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        total = sum(len(recs) for recs in self._records.values())
        promoted = sum(
            1 for recs in self._records.values()
            for r in recs if r.promoted
        )
        demoted = sum(
            1 for recs in self._records.values()
            for r in recs if r.fail_count >= DEMOTE_THRESHOLD
        )
        return {
            "total_records": total,
            "promoted": promoted,
            "demoted": demoted,
            "screens_tracked": len(self._records),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_or_create(
        self, screen_type: str, action_name: str, coords: Tuple[int, int],
    ) -> ActionRecord:
        rec = self._find_record(screen_type, action_name, coords)
        if rec:
            return rec
        new_rec = ActionRecord(
            screen_type=screen_type,
            action_name=action_name,
            coords=coords,
        )
        if screen_type not in self._records:
            self._records[screen_type] = []
        self._records[screen_type].append(new_rec)
        return new_rec

    def _find_record(
        self, screen_type: str, action_name: str, coords: Tuple[int, int],
        tolerance: int = 40,
    ) -> Optional[ActionRecord]:
        for rec in self._records.get(screen_type, []):
            if (rec.action_name == action_name
                    and abs(rec.coords[0] - coords[0]) <= tolerance
                    and abs(rec.coords[1] - coords[1]) <= tolerance):
                return rec
        return None

    def _promote(self, rec: ActionRecord) -> None:
        """Promote a vision action to a BT node."""
        logger.info(
            "OutcomeTracker: PROMOTING '%s' on '%s' at (%d,%d) "
            "(success=%d, fail=%d, source=%s)",
            rec.action_name, rec.screen_type,
            rec.coords[0], rec.coords[1],
            rec.success_count, rec.fail_count, rec.source,
        )
        if self._on_promote:
            self._on_promote(rec.screen_type, {
                "name": rec.action_name,
                "x": rec.coords[0],
                "y": rec.coords[1],
                "action_type": rec.action_type,
                "success_count": rec.success_count,
            })

    def _save(self) -> None:
        if not self._cache_path:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for screen_type, records in self._records.items():
            data[screen_type] = [
                {
                    "action_name": r.action_name,
                    "coords": list(r.coords),
                    "action_type": r.action_type,
                    "success_count": r.success_count,
                    "fail_count": r.fail_count,
                    "last_used": r.last_used,
                    "promoted": r.promoted,
                    "source": r.source,
                }
                for r in records
            ]
        self._cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            for screen_type, records in data.items():
                self._records[screen_type] = [
                    ActionRecord(
                        screen_type=screen_type,
                        action_name=r["action_name"],
                        coords=tuple(r["coords"]),
                        action_type=r.get("action_type", "tap"),
                        success_count=r.get("success_count", 0),
                        fail_count=r.get("fail_count", 0),
                        last_used=r.get("last_used", 0),
                        promoted=r.get("promoted", False),
                        source=r.get("source", "unknown"),
                    )
                    for r in records
                ]
        except Exception as e:
            logger.warning("OutcomeTracker: failed to load cache: %s", e)
            self._records = {}
