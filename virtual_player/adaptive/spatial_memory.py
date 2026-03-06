"""
Spatial Memory -- Zone Awareness
=================================
Remembers what is available in each game screen/zone:
resources, danger level, visit frequency, and known elements.

Persists to a JSON cache file between sessions.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..adb import log


@dataclass
class ZoneInfo:
    """Information about a game screen / zone."""

    screen_type: str
    visit_count: int = 0
    last_visited: float = 0.0
    elements_found: List[str] = field(default_factory=list)
    resources_available: List[str] = field(default_factory=list)  # "potion", "gold_shop", …
    danger_level: float = 0.0      # 0 = safe, 1 = deadly
    avg_hp_change: float = 0.0     # average HP delta observed while here


class SpatialMemory:
    """Spatial awareness -- remember what is in each zone."""

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self._zones: Dict[str, ZoneInfo] = {}
        self._cache_path = cache_path
        if cache_path and cache_path.exists():
            self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe_zone(self, screen_type: str, snapshot, nav_graph=None) -> None:
        """Update zone info based on the current observation."""
        zone = self._get_or_create(screen_type)
        zone.visit_count += 1
        zone.last_visited = time.time()

        # Infer available resources from screen type name
        lower = screen_type.lower()
        if "shop" in lower:
            for res in ("potion", "equipment"):
                if res not in zone.resources_available:
                    zone.resources_available.append(res)
        if "inventory" in lower:
            if "items" not in zone.resources_available:
                zone.resources_available.append("items")
        if "battle" in lower or "combat" in lower or "dungeon" in lower:
            zone.danger_level = max(zone.danger_level, 0.5)
        if "lobby" in lower or "main" in lower or "hub" in lower or "town" in lower:
            if "hub" not in zone.resources_available:
                zone.resources_available.append("hub")

        # Update running average of HP change
        hp = getattr(snapshot, "hp_pct", None)
        if hp is not None and zone.visit_count > 1:
            zone.avg_hp_change = (
                zone.avg_hp_change * (zone.visit_count - 1) + (hp - 0.5)
            ) / zone.visit_count
            # Infer danger from consistent HP loss
            if zone.avg_hp_change < -0.1:
                zone.danger_level = min(1.0, zone.danger_level + 0.05)

        # Absorb element names from nav_graph if provided
        if nav_graph is not None:
            nodes = getattr(nav_graph, "nodes", {})
            if screen_type in nodes:
                node = nodes[screen_type]
                for elem in getattr(node, "elements", []):
                    if elem not in zone.elements_found:
                        zone.elements_found.append(elem)

        self._save()

    def find_zone_with_resource(self, resource: str) -> Optional[str]:
        """Return the most-visited zone that has a given resource, or None."""
        candidates = [
            z for z in self._zones.values()
            if resource in z.resources_available
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda z: z.visit_count, reverse=True)
        return candidates[0].screen_type

    def get_unexplored_zones(self, all_screen_types: List[str]) -> List[str]:
        """Return zones from all_screen_types that have never been visited."""
        return [
            s for s in all_screen_types
            if s not in self._zones or self._zones[s].visit_count == 0
        ]

    def get_safe_zones(self) -> List[str]:
        """Return visited zones with danger_level < 0.3."""
        return [
            z.screen_type
            for z in self._zones.values()
            if z.danger_level < 0.3 and z.visit_count > 0
        ]

    def get_zone_info(self, screen_type: str) -> Optional[ZoneInfo]:
        return self._zones.get(screen_type)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create(self, screen_type: str) -> ZoneInfo:
        if screen_type not in self._zones:
            self._zones[screen_type] = ZoneInfo(screen_type=screen_type)
        return self._zones[screen_type]

    def _save(self) -> None:
        if not self._cache_path:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, dict] = {}
        for st, z in self._zones.items():
            data[st] = {
                "visit_count": z.visit_count,
                "last_visited": z.last_visited,
                "elements_found": z.elements_found,
                "resources_available": z.resources_available,
                "danger_level": z.danger_level,
                "avg_hp_change": z.avg_hp_change,
            }
        self._cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            for st, d in data.items():
                self._zones[st] = ZoneInfo(
                    screen_type=st,
                    visit_count=d.get("visit_count", 0),
                    last_visited=d.get("last_visited", 0.0),
                    elements_found=d.get("elements_found", []),
                    resources_available=d.get("resources_available", []),
                    danger_level=d.get("danger_level", 0.0),
                    avg_hp_change=d.get("avg_hp_change", 0.0),
                )
        except Exception as e:
            log(f"  [SpatialMemory] Failed to load cache: {e}")
            self._zones = {}
