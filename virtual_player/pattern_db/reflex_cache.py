"""
Reflex Cache (L0)
==================
screen_hash + context -> action mapping.
Instant decision lookup for previously seen situations.
Target: <50ms per decision.

Learning: Every L2 (Vision API) decision is stored here.
Next time the same screen appears, L0 handles it instantly.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CachedAction:
    """A cached decision for a specific screen state."""
    action_type: str        # "tap" | "swipe" | "back" | "wait"
    x: int = 0
    y: int = 0
    x2: int = 0             # swipe end
    y2: int = 0
    description: str = ""
    success_count: int = 1
    fail_count: int = 0
    last_used: float = 0.0

    @property
    def reliability(self) -> float:
        """Success rate of this cached action (0.0 ~ 1.0)."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5
        return self.success_count / total


class ReflexCache:
    """L0 reflex cache: screen_hash + screen_type -> action.

    Two lookup keys:
    1. phash (perceptual hash) -- exact visual match (<50ms)
    2. screen_type + context_key -- type-level match (for common patterns)

    Both map to CachedAction with reliability tracking.
    """

    HASH_THRESHOLD = 8      # Max hamming distance for phash match
    MIN_RELIABILITY = 0.3   # Below this, don't use cached action

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = cache_dir / "reflex_cache.json"

        # phash -> list of CachedAction (multiple actions possible per screen)
        self._hash_actions: Dict[int, List[CachedAction]] = {}
        # "screen_type:context" -> list of CachedAction
        self._type_actions: Dict[str, List[CachedAction]] = {}

        self._stats = {"l0_hits": 0, "l0_misses": 0}
        self._load()

    def lookup_by_hash(self, img_hash: int) -> Optional[CachedAction]:
        """Find best action for a perceptual hash (L0 -- <50ms)."""
        best_action = None
        best_dist = self.HASH_THRESHOLD + 1

        for cached_hash, actions in self._hash_actions.items():
            dist = bin(img_hash ^ cached_hash).count("1")
            if dist < best_dist:
                # Pick the most reliable action
                reliable = [a for a in actions if a.reliability >= self.MIN_RELIABILITY]
                if reliable:
                    best_dist = dist
                    best_action = max(reliable, key=lambda a: a.reliability)

        if best_action:
            self._stats["l0_hits"] += 1
            return best_action

        self._stats["l0_misses"] += 1
        return None

    def lookup_by_type(self, screen_type: str, context: str = "") -> Optional[CachedAction]:
        """Find best action for a screen type + context (L0.5)."""
        key = f"{screen_type}:{context}" if context else screen_type
        actions = self._type_actions.get(key, [])
        reliable = [a for a in actions if a.reliability >= self.MIN_RELIABILITY]
        if reliable:
            return max(reliable, key=lambda a: a.reliability)
        return None

    def store(self, img_hash: Optional[int], screen_type: str,
              action: CachedAction, context: str = ""):
        """Store a new action decision (called after L2 Vision decision)."""
        action.last_used = time.time()

        # Store by hash
        if img_hash is not None:
            if img_hash not in self._hash_actions:
                self._hash_actions[img_hash] = []
            # Merge with existing similar action or add new
            merged = False
            for existing in self._hash_actions[img_hash]:
                if (existing.action_type == action.action_type
                        and abs(existing.x - action.x) < 50
                        and abs(existing.y - action.y) < 50):
                    existing.success_count += 1
                    existing.last_used = action.last_used
                    merged = True
                    break
            if not merged:
                self._hash_actions[img_hash].append(action)

        # Store by type
        key = f"{screen_type}:{context}" if context else screen_type
        if key not in self._type_actions:
            self._type_actions[key] = []
        merged = False
        for existing in self._type_actions[key]:
            if (existing.action_type == action.action_type
                    and abs(existing.x - action.x) < 50
                    and abs(existing.y - action.y) < 50):
                existing.success_count += 1
                existing.last_used = action.last_used
                merged = True
                break
        if not merged:
            self._type_actions[key].append(action)

    def invalidate_by_type(self, screen_type: str, context: str = ""):
        """Remove cached actions for a screen_type+context key."""
        key = f"{screen_type}:{context}" if context else screen_type
        if key in self._type_actions:
            del self._type_actions[key]

    def record_outcome(self, img_hash: Optional[int], screen_type: str,
                       action: CachedAction, success: bool):
        """Record whether a cached action succeeded or failed."""
        # Update hash-based entry
        if img_hash is not None and img_hash in self._hash_actions:
            for existing in self._hash_actions[img_hash]:
                if (existing.action_type == action.action_type
                        and abs(existing.x - action.x) < 50
                        and abs(existing.y - action.y) < 50):
                    if success:
                        existing.success_count += 1
                    else:
                        existing.fail_count += 1
                    break

    def get_stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        total_hash_entries = sum(len(v) for v in self._hash_actions.values())
        total_type_entries = sum(len(v) for v in self._type_actions.values())
        return {
            **self._stats,
            "hash_entries": total_hash_entries,
            "type_entries": total_type_entries,
        }

    def save(self):
        """Persist cache to disk."""
        data = {
            "hash_actions": {
                str(h): [self._action_to_dict(a) for a in actions]
                for h, actions in self._hash_actions.items()
            },
            "type_actions": {
                k: [self._action_to_dict(a) for a in actions]
                for k, actions in self._type_actions.items()
            },
        }
        self._cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load(self):
        """Load cache from disk."""
        if not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            for h_str, actions in data.get("hash_actions", {}).items():
                self._hash_actions[int(h_str)] = [self._dict_to_action(a) for a in actions]
            for key, actions in data.get("type_actions", {}).items():
                self._type_actions[key] = [self._dict_to_action(a) for a in actions]
        except Exception:
            pass

    @staticmethod
    def _action_to_dict(a: CachedAction) -> dict:
        return {
            "action_type": a.action_type,
            "x": a.x, "y": a.y,
            "x2": a.x2, "y2": a.y2,
            "description": a.description,
            "success_count": a.success_count,
            "fail_count": a.fail_count,
            "last_used": a.last_used,
        }

    @staticmethod
    def _dict_to_action(d: dict) -> CachedAction:
        return CachedAction(
            action_type=d.get("action_type", "tap"),
            x=d.get("x", 0), y=d.get("y", 0),
            x2=d.get("x2", 0), y2=d.get("y2", 0),
            description=d.get("description", ""),
            success_count=d.get("success_count", 1),
            fail_count=d.get("fail_count", 0),
            last_used=d.get("last_used", 0.0),
        )
