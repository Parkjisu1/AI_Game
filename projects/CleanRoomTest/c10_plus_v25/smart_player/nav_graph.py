"""
Navigation Graph
=================
Screen transition graph built from recorded gameplay.
Nodes = screen types, Edges = actions that transition between screens.
"""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core import SYS_CFG, log


@dataclass
class NavNode:
    """A screen type node in the navigation graph."""
    screen_type: str
    visit_count: int = 0
    sample_screenshots: List[str] = field(default_factory=list)  # max 3

    def add_sample(self, path: str):
        if len(self.sample_screenshots) < 3:
            self.sample_screenshots.append(path)


@dataclass
class NavAction:
    """An action that causes a screen transition."""
    action_type: str    # "tap" | "swipe" | "back"
    x: int = 0
    y: int = 0
    x2: int = 0         # swipe end
    y2: int = 0
    description: str = ""


@dataclass
class NavEdge:
    """A directed edge: source --action--> target."""
    source: str          # source screen_type
    target: str          # target screen_type
    action: NavAction
    success_count: int = 1


class NavigationGraph:
    """Directed graph of screen transitions."""

    COORD_MERGE_THRESHOLD = 80  # pixels — edges with similar coords merge

    def __init__(self):
        self.nodes: Dict[str, NavNode] = {}
        self.edges: List[NavEdge] = []

    # --- Query ---

    def find_path(self, source: str, target: str) -> Optional[List[NavEdge]]:
        """BFS shortest path from source to target screen type.

        Returns list of edges to traverse, or None if unreachable.
        """
        if source == target:
            return []
        if source not in self.nodes or target not in self.nodes:
            return None

        # BFS
        queue = deque([(source, [])])
        visited = {source}

        while queue:
            current, path = queue.popleft()
            for edge in self.get_edges_from(current):
                if edge.target in visited:
                    continue
                new_path = path + [edge]
                if edge.target == target:
                    return new_path
                visited.add(edge.target)
                queue.append((edge.target, new_path))

        return None  # Unreachable

    def get_edges_from(self, screen_type: str) -> List[NavEdge]:
        """Get all outgoing edges from a screen type, sorted by success_count desc."""
        edges = [e for e in self.edges if e.source == screen_type]
        edges.sort(key=lambda e: e.success_count, reverse=True)
        return edges

    def get_all_screen_types(self) -> List[str]:
        """Return all known screen types in the graph."""
        return list(self.nodes.keys())

    # --- Build ---

    def add_node(self, screen_type: str, screenshot_path: str = ""):
        """Add or update a node."""
        if screen_type not in self.nodes:
            self.nodes[screen_type] = NavNode(screen_type=screen_type)
        node = self.nodes[screen_type]
        node.visit_count += 1
        if screenshot_path:
            node.add_sample(screenshot_path)

    def add_edge(self, source: str, target: str, action: NavAction):
        """Add an edge or merge with existing similar edge."""
        if source == target:
            return  # No self-loops

        # Try to merge with existing edge
        for edge in self.edges:
            if (edge.source == source and edge.target == target
                    and edge.action.action_type == action.action_type
                    and self._coords_similar(edge.action, action)):
                edge.success_count += 1
                return

        self.edges.append(NavEdge(
            source=source, target=target, action=action, success_count=1
        ))

    def _coords_similar(self, a1: NavAction, a2: NavAction) -> bool:
        """Check if two actions target approximately the same coordinates."""
        dx = abs(a1.x - a2.x)
        dy = abs(a1.y - a2.y)
        return dx < self.COORD_MERGE_THRESHOLD and dy < self.COORD_MERGE_THRESHOLD

    # --- Build from Recording ---

    @staticmethod
    def build_from_recording(
        recording_path: Path,
        classifications: Dict[str, str],
    ) -> "NavigationGraph":
        """Build navigation graph from recording.json + classified frames.

        Supports two modes:
        1. Event-based: uses touch events with screenshot_before/after
        2. Frame-sequence: uses consecutive frame transitions (no events needed)
           This mode works on BlueStacks where getevent can't capture touches.

        Args:
            recording_path: Path to recording.json
            classifications: {frame_filename: screen_type} mapping
        """
        graph = NavigationGraph()

        data = json.loads(recording_path.read_text(encoding="utf-8"))
        events = data.get("events", [])

        # --- Mode 1: Event-based (if events available) ---
        if events:
            for event in events:
                before_frame = event.get("screenshot_before", "")
                after_frame = event.get("screenshot_after", "")

                before_type = classifications.get(before_frame, "unknown")
                after_type = classifications.get(after_frame, "unknown")

                if before_type == "unknown" or after_type == "unknown":
                    continue

                graph.add_node(before_type, before_frame)
                graph.add_node(after_type, after_frame)

                event_type = event.get("type", "tap")
                if event_type == "tap":
                    action = NavAction(
                        action_type="tap",
                        x=event.get("x", 0),
                        y=event.get("y", 0),
                    )
                elif event_type == "swipe":
                    action = NavAction(
                        action_type="swipe",
                        x=event.get("x1", 0),
                        y=event.get("y1", 0),
                        x2=event.get("x2", 0),
                        y2=event.get("y2", 0),
                    )
                else:
                    continue

                if before_type != after_type:
                    graph.add_edge(before_type, after_type, action)

            log(f"  [NavGraph] Built from events: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
            return graph

        # --- Mode 2: Frame-sequence (no events — e.g. BlueStacks) ---
        log("  [NavGraph] No touch events found, building from frame sequence...")
        sorted_frames = sorted(classifications.keys())

        for frame_name in sorted_frames:
            screen_type = classifications[frame_name]
            if screen_type != "unknown":
                graph.add_node(screen_type, frame_name)

        # Create edges from consecutive frames with different screen types
        for i in range(len(sorted_frames) - 1):
            curr_frame = sorted_frames[i]
            next_frame = sorted_frames[i + 1]
            curr_type = classifications.get(curr_frame, "unknown")
            next_type = classifications.get(next_frame, "unknown")

            if curr_type == "unknown" or next_type == "unknown":
                continue
            if curr_type == next_type:
                continue

            # Transition detected — create edge with "vision" action type
            # (AI will use Claude Vision to determine exact tap location)
            action = NavAction(
                action_type="vision",  # signals AI to use vision for navigation
                description=f"Screen changed: {curr_frame} → {next_frame}",
            )
            graph.add_edge(curr_type, next_type, action)

        # --- Add implicit reverse edges ---
        # In frame-sequence mode, we only see recorded transitions.
        # Most game screens have a "back" navigation, so add reverse edges
        # where they don't already exist. This allows the navigator to
        # find paths back to hub screens (lobby, menu_inventory, etc.)
        existing_pairs = {(e.source, e.target) for e in graph.edges}
        reverse_edges_added = 0
        for edge in list(graph.edges):
            reverse_pair = (edge.target, edge.source)
            if reverse_pair not in existing_pairs:
                reverse_action = NavAction(
                    action_type="vision",
                    description=f"Reverse of: {edge.source} → {edge.target} (implicit back)",
                )
                graph.edges.append(NavEdge(
                    source=edge.target,
                    target=edge.source,
                    action=reverse_action,
                    success_count=1,
                ))
                existing_pairs.add(reverse_pair)
                reverse_edges_added += 1

        log(f"  [NavGraph] Built from frames: {len(graph.nodes)} nodes, "
            f"{len(graph.edges)} edges ({reverse_edges_added} reverse added)")
        return graph

    # --- Persistence ---

    def save(self, path: Path):
        """Save graph to JSON file."""
        data = {
            "nodes": {
                k: {
                    "screen_type": v.screen_type,
                    "visit_count": v.visit_count,
                    "sample_screenshots": v.sample_screenshots,
                }
                for k, v in self.nodes.items()
            },
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "action": {
                        "action_type": e.action.action_type,
                        "x": e.action.x,
                        "y": e.action.y,
                        "x2": e.action.x2,
                        "y2": e.action.y2,
                        "description": e.action.description,
                    },
                    "success_count": e.success_count,
                }
                for e in self.edges
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"  [NavGraph] Saved to {path}")

    @staticmethod
    def load(path: Path) -> "NavigationGraph":
        """Load graph from JSON file."""
        graph = NavigationGraph()
        data = json.loads(path.read_text(encoding="utf-8"))

        for k, v in data.get("nodes", {}).items():
            node = NavNode(
                screen_type=v["screen_type"],
                visit_count=v.get("visit_count", 0),
                sample_screenshots=v.get("sample_screenshots", []),
            )
            graph.nodes[k] = node

        for e in data.get("edges", []):
            act = e.get("action", {})
            edge = NavEdge(
                source=e["source"],
                target=e["target"],
                action=NavAction(
                    action_type=act.get("action_type", "tap"),
                    x=act.get("x", 0),
                    y=act.get("y", 0),
                    x2=act.get("x2", 0),
                    y2=act.get("y2", 0),
                    description=act.get("description", ""),
                ),
                success_count=e.get("success_count", 1),
            )
            graph.edges.append(edge)

        log(f"  [NavGraph] Loaded: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        return graph
