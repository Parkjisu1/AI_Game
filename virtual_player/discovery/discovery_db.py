"""
DiscoveryDB -- Persistent UI Element Memory
============================================
Tracks discovered screen elements, screen transitions, and dead zones (unresponsive areas).
Provides BFS pathfinding over the transition graph.

Extracted from smart_player.py and made game-agnostic.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DiscoveryDB:
    """Persistent JSON database for discovered UI elements, transitions, and dead zones."""

    COORD_TOLERANCE = 50      # pixels -- merge threshold for nearby taps
    FAIL_THRESHOLD = 3        # taps needed to mark zone as dead
    MAX_ELEMENTS = 50         # per screen
    MAX_FAILED = 200          # dead zones max

    def __init__(
        self,
        db_path: Optional[Path] = None,
        seed_data: Optional[Dict[str, Any]] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        """
        Args:
            db_path: Where to persist the JSON DB. None = in-memory only.
            seed_data: Initial data dict with 'screens', 'transitions', 'failed_taps'.
                       If None and db_path doesn't exist, starts empty.
            screen_width: Device screen width in pixels.
            screen_height: Device screen height in pixels.
        """
        self.db_path = Path(db_path) if db_path else None
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.screens: Dict[str, Dict[str, Any]] = {}
        self.transitions: List[Dict[str, Any]] = []
        self.failed_taps: List[Dict[str, Any]] = []

        loaded = self._load()
        if not loaded and seed_data:
            self.screens = seed_data.get("screens", {})
            self.transitions = seed_data.get("transitions", [])
            self.failed_taps = seed_data.get("failed_taps", [])

    def _load(self) -> bool:
        """Load DB from disk. Returns True if loaded successfully."""
        if not self.db_path or not self.db_path.exists():
            return False
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.screens = data.get("screens", {})
            self.transitions = data.get("transitions", [])
            self.failed_taps = data.get("failed_taps", [])
            return True
        except Exception as e:
            logger.warning("Failed to load DiscoveryDB from %s: %s", self.db_path, e)
            self.screens = {}
            self.transitions = []
            self.failed_taps = []
            return False

    def save(self) -> None:
        """Persist DB to disk with atomic write (tmp + rename)."""
        if not self.db_path:
            return

        # Trim elements per screen
        for sdata in self.screens.values():
            elems = sdata.get("elements", [])
            if len(elems) > self.MAX_ELEMENTS:
                elems.sort(key=lambda e: e.get("tap_count", 0), reverse=True)
                sdata["elements"] = elems[:self.MAX_ELEMENTS]

        # Trim dead zones
        if len(self.failed_taps) > self.MAX_FAILED:
            self.failed_taps.sort(key=lambda f: f.get("fail_count", 0), reverse=True)
            self.failed_taps = self.failed_taps[:self.MAX_FAILED]

        data = {
            "screens": self.screens,
            "transitions": self.transitions,
            "failed_taps": self.failed_taps,
        }

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.db_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(self.db_path)
        except OSError:
            if self.db_path.exists():
                self.db_path.unlink()
            tmp.rename(self.db_path)

    # ------------------------------------------------------------------
    # Record operations
    # ------------------------------------------------------------------

    def record_element(
        self,
        screen: str,
        x: int,
        y: int,
        ocr_text: str = "",
        target_screen: str = "",
        success: bool = True,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Record a discovered UI element. Deduplicates within COORD_TOLERANCE."""
        if screen not in self.screens:
            self.screens[screen] = {"visit_count": 0, "elements": [], "tags": []}

        elements = self.screens[screen]["elements"]
        for elem in elements:
            if (abs(elem["x"] - x) <= self.COORD_TOLERANCE and
                    abs(elem["y"] - y) <= self.COORD_TOLERANCE):
                elem["tap_count"] = elem.get("tap_count", 0) + 1
                if success:
                    elem["success_count"] = elem.get("success_count", 0) + 1
                if ocr_text and not elem.get("ocr_text"):
                    elem["ocr_text"] = ocr_text
                if target_screen and target_screen != "unknown":
                    elem["target_screen"] = target_screen
                if tags:
                    existing_tags = set(elem.get("tags", []))
                    existing_tags.update(tags)
                    elem["tags"] = list(existing_tags)
                return

        elements.append({
            "x": x, "y": y,
            "label": ocr_text or f"elem_{x}_{y}",
            "ocr_text": ocr_text or "",
            "target_screen": target_screen or "",
            "tap_count": 1,
            "success_count": 1 if success else 0,
            "tags": tags or [],
            "source": "explored",
        })

    def record_transition(
        self,
        from_screen: str,
        to_screen: str,
        steps: List[Dict[str, Any]],
    ) -> None:
        """Record a screen-to-screen transition. Increments count if already known."""
        for t in self.transitions:
            if t["from_screen"] == from_screen and t["to_screen"] == to_screen:
                t["success_count"] = t.get("success_count", 0) + 1
                return
        self.transitions.append({
            "from_screen": from_screen,
            "to_screen": to_screen,
            "via": steps,
            "success_count": 1,
        })

    def record_failure(self, screen: str, x: int, y: int) -> None:
        """Record a failed tap (unresponsive area)."""
        for f in self.failed_taps:
            if (f["screen_type"] == screen and
                    abs(f["x"] - x) <= self.COORD_TOLERANCE and
                    abs(f["y"] - y) <= self.COORD_TOLERANCE):
                f["fail_count"] = f.get("fail_count", 0) + 1
                f["last_failed"] = datetime.now().isoformat()
                return
        self.failed_taps.append({
            "screen_type": screen,
            "x": x, "y": y,
            "fail_count": 1,
            "last_failed": datetime.now().isoformat(),
        })

    def record_visit(self, screen: str) -> None:
        """Increment visit count for a screen."""
        if screen not in self.screens:
            self.screens[screen] = {"visit_count": 0, "elements": [], "tags": []}
        self.screens[screen]["visit_count"] = self.screens[screen].get("visit_count", 0) + 1

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def is_dead_zone(self, screen: str, x: int, y: int) -> bool:
        """Returns True if (x, y) on screen has failed >= FAIL_THRESHOLD times."""
        for f in self.failed_taps:
            if (f["screen_type"] == screen and
                    abs(f["x"] - x) <= self.COORD_TOLERANCE and
                    abs(f["y"] - y) <= self.COORD_TOLERANCE and
                    f.get("fail_count", 0) >= self.FAIL_THRESHOLD):
                return True
        return False

    def get_untapped_regions(
        self,
        screen: str,
        cols: int = 5,
        rows: int = 8,
        margin_top_pct: float = 0.05,
        margin_bottom_pct: float = 0.08,
    ) -> List[Tuple[int, int]]:
        """Return grid cell centers not covered by known elements or dead zones."""
        w, h = self.screen_width, self.screen_height
        margin_top = int(h * margin_top_pct)
        margin_bottom = int(h * margin_bottom_pct)
        cell_w = w // cols
        cell_h = (h - margin_top - margin_bottom) // rows

        elements = []
        if screen in self.screens:
            elements = self.screens[screen].get("elements", [])

        points = []
        for r in range(rows):
            for c in range(cols):
                cx = c * cell_w + cell_w // 2
                cy = margin_top + r * cell_h + cell_h // 2

                covered = any(
                    abs(elem["x"] - cx) <= cell_w // 2 and
                    abs(elem["y"] - cy) <= cell_h // 2
                    for elem in elements
                )
                if covered:
                    continue
                if self.is_dead_zone(screen, cx, cy):
                    continue
                points.append((cx, cy))

        return points

    def find_path_to(self, keyword: str) -> Optional[List[Dict[str, Any]]]:
        """BFS over transitions graph to find path to screen containing keyword."""
        keyword_lower = keyword.lower()

        # Find target screens containing the keyword
        target_screens = set()
        for stype, sdata in self.screens.items():
            for elem in sdata.get("elements", []):
                text = (elem.get("ocr_text", "") + " " + elem.get("label", "")).lower()
                if keyword_lower in text:
                    target_screens.add(stype)

        if not target_screens:
            return None

        # Build adjacency list
        adj: Dict[str, List[Tuple[str, List]]] = {}
        for t in self.transitions:
            src = t["from_screen"]
            if src not in adj:
                adj[src] = []
            adj[src].append((t["to_screen"], t["via"]))

        # BFS from each known start screen
        start_screens = list(self.screens.keys())
        for start in start_screens:
            # Direct match on start screen
            if start in target_screens:
                for elem in self.screens[start].get("elements", []):
                    text = (elem.get("ocr_text", "") + " " + elem.get("label", "")).lower()
                    if keyword_lower in text:
                        return [{"action": "tap", "x": elem["x"], "y": elem["y"],
                                 "label": elem.get("label", "")}]

            queue: List[Tuple[str, List]] = [(start, [])]
            visited = {start}
            while queue:
                current, path = queue.pop(0)
                for neighbor, via in adj.get(current, []):
                    if neighbor in visited:
                        continue
                    new_path = path + via
                    if neighbor in target_screens:
                        for elem in self.screens[neighbor].get("elements", []):
                            text = (elem.get("ocr_text", "") + " " + elem.get("label", "")).lower()
                            if keyword_lower in text:
                                return new_path + [
                                    {"action": "tap", "x": elem["x"], "y": elem["y"],
                                     "label": elem.get("label", "")}
                                ]
                        return new_path
                    visited.add(neighbor)
                    queue.append((neighbor, new_path))

        return None

    def find_element(self, screen: str, keyword: str) -> Optional[Tuple[int, int]]:
        """Find element coordinates by keyword on a specific screen."""
        keyword_lower = keyword.lower()
        if screen not in self.screens:
            return None
        for elem in self.screens[screen].get("elements", []):
            text = (elem.get("ocr_text", "") + " " + elem.get("label", "")).lower()
            if keyword_lower in text:
                return (elem["x"], elem["y"])
        return None

    def get_screen_names(self) -> List[str]:
        """Return all known screen names."""
        return list(self.screens.keys())

    def get_elements(self, screen: str) -> List[Dict[str, Any]]:
        """Return all elements for a screen."""
        if screen not in self.screens:
            return []
        return self.screens[screen].get("elements", [])

    def get_transitions_from(self, screen: str) -> List[Dict[str, Any]]:
        """Return all transitions originating from a screen."""
        return [t for t in self.transitions if t["from_screen"] == screen]

    def to_dict(self) -> Dict[str, Any]:
        """Export the full DB as a dictionary."""
        return {
            "screens": self.screens,
            "transitions": self.transitions,
            "failed_taps": self.failed_taps,
        }

    def merge(self, other: "DiscoveryDB") -> None:
        """Merge another DiscoveryDB into this one."""
        for stype, sdata in other.screens.items():
            if stype not in self.screens:
                self.screens[stype] = sdata
            else:
                for elem in sdata.get("elements", []):
                    self.record_element(
                        stype, elem["x"], elem["y"],
                        ocr_text=elem.get("ocr_text", ""),
                        target_screen=elem.get("target_screen", ""),
                        success=elem.get("success_count", 0) > 0,
                        tags=elem.get("tags"),
                    )
        for t in other.transitions:
            self.record_transition(t["from_screen"], t["to_screen"], t["via"])
        for f in other.failed_taps:
            self.record_failure(f["screen_type"], f["x"], f["y"])
