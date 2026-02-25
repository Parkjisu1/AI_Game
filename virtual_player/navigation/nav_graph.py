"""
Navigation Graph (Annotated)
==============================
Screen transition graph + in-screen action patterns.

Nodes = screen types with known UI elements + in-screen actions
Edges = annotated transitions (what element was tapped, category, description)

Ported from C10+ smart_player/nav_graph.py, enhanced with semantic annotation.
"""

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..adb import log


@dataclass
class NavNode:
    """A screen type node in the navigation graph."""
    screen_type: str
    visit_count: int = 0
    sample_screenshots: List[str] = field(default_factory=list)  # max 3
    elements: List[str] = field(default_factory=list)            # known UI elements
    in_screen_actions: List[Dict] = field(default_factory=list)  # same-screen actions

    def add_sample(self, path: str):
        if len(self.sample_screenshots) < 3:
            self.sample_screenshots.append(path)

    def add_element(self, element: str):
        if element and element not in self.elements:
            self.elements.append(element)

    def add_in_screen_action(self, action: Dict):
        """Add or merge a same-screen action (scroll, interaction, idle)."""
        for existing in self.in_screen_actions:
            if (existing.get("element") == action.get("element")
                    and existing.get("category") == action.get("category")):
                existing["count"] = existing.get("count", 1) + 1
                return
        action.setdefault("count", 1)
        self.in_screen_actions.append(action)


@dataclass
class NavAction:
    """An action that causes a screen transition."""
    action_type: str    # "tap" | "swipe" | "back" | "vision"
    x: int = 0
    y: int = 0
    x2: int = 0         # swipe end
    y2: int = 0
    description: str = ""
    element: str = ""    # semantic: "shop_button", "back_icon", "item_slot_3"
    category: str = ""   # "navigation" | "interaction" | "scroll" | "idle"


@dataclass
class NavEdge:
    """A directed edge: source --action--> target."""
    source: str          # source screen_type
    target: str          # target screen_type
    action: NavAction
    success_count: int = 1


class NavigationGraph:
    """Directed graph of screen transitions + in-screen behavior."""

    COORD_MERGE_THRESHOLD = 80  # pixels — edges with similar coords merge

    def __init__(self):
        self.nodes: Dict[str, NavNode] = {}
        self.edges: List[NavEdge] = []
        self.action_log: List[Dict] = []  # ordered sequence of ALL recorded actions

    # --- Query ---

    def find_path(self, source: str, target: str,
                  excluded_edges: set = None) -> Optional[List[NavEdge]]:
        """BFS shortest path from source to target screen type.

        excluded_edges: set of (source, target, element) tuples to skip.
        """
        if source == target:
            return []
        if source not in self.nodes or target not in self.nodes:
            return None

        excluded = excluded_edges or set()
        queue = deque([(source, [])])
        visited = {source}

        while queue:
            current, path = queue.popleft()
            for edge in self.get_edges_from(current):
                if edge.target in visited:
                    continue
                # Skip failed edges
                key = (edge.source, edge.target, edge.action.element)
                if key in excluded:
                    continue
                new_path = path + [edge]
                if edge.target == target:
                    return new_path
                visited.add(edge.target)
                queue.append((edge.target, new_path))

        return None

    def get_edges_from(self, screen_type: str) -> List[NavEdge]:
        """Get all outgoing edges from a screen type, sorted by success_count desc."""
        edges = [e for e in self.edges if e.source == screen_type]
        edges.sort(key=lambda e: e.success_count, reverse=True)
        return edges

    def get_all_screen_types(self) -> List[str]:
        return list(self.nodes.keys())

    def get_hub_nodes(self, top_n: int = 3) -> List[str]:
        """Find the most-connected nodes (hubs) in the graph."""
        edge_counts: Dict[str, int] = {}
        for edge in self.edges:
            edge_counts[edge.source] = edge_counts.get(edge.source, 0) + 1

        hub_priority = ["lobby", "menu_inventory", "menu_shop", "battle"]
        hubs = [h for h in hub_priority if h in self.nodes]

        sorted_nodes = sorted(edge_counts.items(), key=lambda x: x[1], reverse=True)
        for n, _ in sorted_nodes:
            if n not in hubs and len(hubs) < top_n:
                hubs.append(n)

        return hubs[:top_n]

    def get_elements_for_screen(self, screen_type: str) -> List[str]:
        """Get known UI elements for a screen type."""
        node = self.nodes.get(screen_type)
        if node:
            return list(node.elements)
        return []

    def get_in_screen_actions(self, screen_type: str) -> List[Dict]:
        """Get same-screen actions for a screen type."""
        node = self.nodes.get(screen_type)
        if node:
            return list(node.in_screen_actions)
        return []

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
            return

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
        dx = abs(a1.x - a2.x)
        dy = abs(a1.y - a2.y)
        return dx < self.COORD_MERGE_THRESHOLD and dy < self.COORD_MERGE_THRESHOLD

    # --- Build from Annotated Recording ---

    @staticmethod
    def build_from_annotated(annotations: List[Dict]) -> "NavigationGraph":
        """Build navigation graph from Vision-annotated action list.

        Each annotation dict has:
            before_screen, after_screen, element, category, description,
            action_type, x, y, [x2, y2], screenshot_before, screenshot_after
        """
        graph = NavigationGraph()
        graph.action_log = list(annotations)

        for i, ann in enumerate(annotations):
            before_type = ann.get("before_screen", "unknown")
            after_type = ann.get("after_screen", "unknown")
            category = ann.get("category", "unknown")
            element = ann.get("element", "")
            description = ann.get("description", "")

            if before_type == "unknown":
                continue

            # Always add nodes
            graph.add_node(before_type, ann.get("screenshot_before", ""))
            if after_type != "unknown":
                graph.add_node(after_type, ann.get("screenshot_after", ""))

            # Register element on the source node
            if element:
                graph.nodes[before_type].add_element(element)

            action = NavAction(
                action_type=ann.get("action_type", "tap"),
                x=ann.get("x", 0),
                y=ann.get("y", 0),
                x2=ann.get("x2", 0),
                y2=ann.get("y2", 0),
                description=description,
                element=element,
                category=category,
            )

            if category == "navigation" and before_type != after_type:
                # Screen transition → graph edge
                graph.add_edge(before_type, after_type, action)
            elif category in ("scroll", "interaction", "idle"):
                # Same-screen action → node's in_screen_actions
                in_action = {
                    "action_type": action.action_type,
                    "x": action.x, "y": action.y,
                    "x2": action.x2, "y2": action.y2,
                    "element": element,
                    "category": category,
                    "description": description,
                }
                graph.nodes[before_type].add_in_screen_action(in_action)

        nav_count = sum(1 for a in annotations if a.get("category") == "navigation")
        inscreen_count = sum(1 for a in annotations if a.get("category") in ("scroll", "interaction"))
        idle_count = sum(1 for a in annotations if a.get("category") == "idle")
        log(f"  [NavGraph] Built: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        log(f"    navigation={nav_count}, scroll/interaction={inscreen_count}, idle={idle_count}")

        return graph

    @staticmethod
    def build_from_recording(
        recording_path: Path,
        classifications: Dict[str, str],
    ) -> "NavigationGraph":
        """Build navigation graph from recording.json + classified frames (legacy).

        For annotated builds, use build_from_annotated() instead.
        """
        graph = NavigationGraph()
        data = json.loads(recording_path.read_text(encoding="utf-8"))
        events = data.get("events", [])

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
                        x=event.get("x", 0), y=event.get("y", 0),
                    )
                elif event_type == "swipe":
                    action = NavAction(
                        action_type="swipe",
                        x=event.get("x1", 0), y=event.get("y1", 0),
                        x2=event.get("x2", 0), y2=event.get("y2", 0),
                    )
                else:
                    continue

                if before_type != after_type:
                    graph.add_edge(before_type, after_type, action)

            log(f"  [NavGraph] Built from events: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
            return graph

        # Frame-sequence fallback
        log("  [NavGraph] No touch events found, building from frame sequence...")
        sorted_frames = sorted(classifications.keys())
        for frame_name in sorted_frames:
            screen_type = classifications[frame_name]
            if screen_type != "unknown":
                graph.add_node(screen_type, frame_name)

        for i in range(len(sorted_frames) - 1):
            curr_type = classifications.get(sorted_frames[i], "unknown")
            next_type = classifications.get(sorted_frames[i + 1], "unknown")
            if curr_type == "unknown" or next_type == "unknown" or curr_type == next_type:
                continue
            action = NavAction(action_type="vision",
                               description=f"Screen changed: {sorted_frames[i]} -> {sorted_frames[i+1]}")
            graph.add_edge(curr_type, next_type, action)

        existing_pairs = {(e.source, e.target) for e in graph.edges}
        for edge in list(graph.edges):
            reverse_pair = (edge.target, edge.source)
            if reverse_pair not in existing_pairs:
                graph.edges.append(NavEdge(
                    source=edge.target, target=edge.source,
                    action=NavAction(action_type="vision",
                                     description=f"Implicit reverse: {edge.target} -> {edge.source}"),
                    success_count=1,
                ))
                existing_pairs.add(reverse_pair)

        log(f"  [NavGraph] Built from frames: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
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
                    "elements": v.elements,
                    "in_screen_actions": v.in_screen_actions,
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
                        "element": e.action.element,
                        "category": e.action.category,
                    },
                    "success_count": e.success_count,
                }
                for e in self.edges
            ],
            "action_log": self.action_log,
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
                elements=v.get("elements", []),
                in_screen_actions=v.get("in_screen_actions", []),
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
                    element=act.get("element", ""),
                    category=act.get("category", ""),
                ),
                success_count=e.get("success_count", 1),
            )
            graph.edges.append(edge)

        graph.action_log = data.get("action_log", [])

        log(f"  [NavGraph] Loaded: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        return graph
