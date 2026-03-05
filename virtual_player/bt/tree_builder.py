"""
BT Tree Builder
================
Builds per-screen behavior trees from:
  1. Nav graph (known edges + in_screen_actions)
  2. Promoted nodes (from OutcomeTracker)
  3. Genre schema (screen type definitions)

Each screen gets a 3-layer Selector:
  Layer 1: Known BT nodes (from DB/nav_graph + promoted nodes)
  Layer 2: Discovery (grid taps)
  Layer 3: Vision AI fallback
"""

import logging
from typing import Any, Dict, List, Optional

from .nodes import (
    BTNode,
    BackKeyAction,
    Condition,
    DiscoveryTap,
    EpsilonRandom,
    PersonaGate,
    Selector,
    Sequence,
    Status,
    SwipeAction,
    TapAction,
    VisionQuery,
    WaitAction,
)

logger = logging.getLogger(__name__)


class ScreenBehaviorTree:
    """Holds the BT root for a specific screen type."""

    def __init__(self, screen_type: str, root: BTNode):
        self.screen_type = screen_type
        self.root = root

    def __repr__(self):
        return f"ScreenBT({self.screen_type}, root={self.root.name})"


class TreeBuilder:
    """Builds behavior trees per screen from nav_graph and promoted actions."""

    def __init__(
        self,
        nav_graph: Any = None,
        promoted_actions: Optional[Dict[str, List[Dict]]] = None,
        epsilon: float = 0.1,
    ):
        self._graph = nav_graph
        self._promoted = promoted_actions or {}
        self._epsilon = epsilon
        self._trees: Dict[str, ScreenBehaviorTree] = {}

    def build_all(self, screen_types: Optional[List[str]] = None) -> Dict[str, ScreenBehaviorTree]:
        """Build trees for all known screen types."""
        types = screen_types or []

        # Add screen types from nav graph
        if self._graph:
            for node_id in self._graph.nodes:
                if node_id not in types:
                    types.append(node_id)

        # Add screen types from promoted actions
        for screen in self._promoted:
            if screen not in types:
                types.append(screen)

        # Always include universal screens
        for s in ("unknown", "ad", "popup"):
            if s not in types:
                types.append(s)

        for screen_type in types:
            self._trees[screen_type] = self.build_one(screen_type)

        logger.info("TreeBuilder: built %d screen trees", len(self._trees))
        return self._trees

    # Screens where Vision AI should drive gameplay (not nav_graph edges)
    VISION_FIRST_SCREENS = {"gameplay", "battle", "puzzle", "board"}

    def build_one(self, screen_type: str) -> ScreenBehaviorTree:
        """Build a 3-layer behavior tree for one screen."""
        layer1_nodes = self._build_known_actions(screen_type)
        layer2 = DiscoveryTap(name=f"discover_{screen_type}")
        layer3 = VisionQuery(name=f"vision_{screen_type}")

        # Wrap known actions with epsilon-random for diversity
        if layer1_nodes:
            layer1 = EpsilonRandom(
                name=f"known_{screen_type}",
                children=layer1_nodes,
                epsilon=self._epsilon,
            )
        else:
            layer1 = None

        # For gameplay screens: Vision first, then known actions as fallback
        if screen_type in self.VISION_FIRST_SCREENS:
            children: List[BTNode] = [layer3]  # Vision first
            if layer1:
                children.append(layer1)
            children.append(layer2)
        else:
            # Normal: known actions -> discovery -> vision
            children = []
            if layer1:
                children.append(layer1)
            children.append(layer2)
            children.append(layer3)

        root = Selector(name=f"root_{screen_type}", children=children)
        return ScreenBehaviorTree(screen_type, root)

    def get_tree(self, screen_type: str) -> Optional[ScreenBehaviorTree]:
        """Get or lazily build a tree for a screen type."""
        if screen_type not in self._trees:
            self._trees[screen_type] = self.build_one(screen_type)
        return self._trees[screen_type]

    def add_promoted_node(self, screen_type: str, action: Dict) -> None:
        """Add a promoted action node and rebuild the tree."""
        if screen_type not in self._promoted:
            self._promoted[screen_type] = []

        # Check for duplicates
        for existing in self._promoted[screen_type]:
            if (existing.get("name") == action.get("name")
                    and existing.get("x") == action.get("x")
                    and existing.get("y") == action.get("y")):
                return

        self._promoted[screen_type].append(action)
        # Rebuild tree for this screen
        self._trees[screen_type] = self.build_one(screen_type)
        logger.info("TreeBuilder: promoted node '%s' added to '%s', tree rebuilt",
                     action.get("name", "?"), screen_type)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_known_actions(self, screen_type: str) -> List[BTNode]:
        """Build leaf nodes from nav_graph + promoted actions."""
        nodes: List[BTNode] = []

        # From nav graph edges (transition actions)
        if self._graph:
            edges = self._graph.get_edges_from(screen_type)
            for edge in edges:
                action = edge.action
                node = TapAction(
                    name=f"edge:{screen_type}->{edge.target}",
                    x=action.x,
                    y=action.y,
                    wait=1.5,
                )
                nodes.append(node)

            # From in-screen actions
            in_screen = self._graph.get_in_screen_actions(screen_type)
            for act in in_screen:
                category = act.get("category", "")
                if category not in ("interaction", "scroll"):
                    continue
                action_type = act.get("action_type", "tap")
                name = f"inscreen:{act.get('element', 'unknown')}"
                if action_type == "swipe":
                    node = SwipeAction(
                        name=name,
                        x1=act.get("x", 540), y1=act.get("y", 960),
                        x2=act.get("x2", 540), y2=act.get("y2", 960),
                    )
                else:
                    node = TapAction(
                        name=name,
                        x=act.get("x", 540),
                        y=act.get("y", 960),
                    )
                nodes.append(node)

        # From promoted actions (learned from VisionQuery successes)
        for act in self._promoted.get(screen_type, []):
            action_type = act.get("action_type", "tap")
            name = act.get("name", "promoted_action")
            if action_type == "swipe":
                node = SwipeAction(
                    name=f"promoted:{name}",
                    x1=act.get("x", 540), y1=act.get("y", 960),
                    x2=act.get("x2", 540), y2=act.get("y2", 960),
                )
            elif action_type == "back":
                node = BackKeyAction(name=f"promoted:{name}")
            elif action_type == "wait":
                node = WaitAction(name=f"promoted:{name}", seconds=act.get("seconds", 2.0))
            else:
                node = TapAction(
                    name=f"promoted:{name}",
                    x=act.get("x", 540),
                    y=act.get("y", 960),
                    wait=act.get("wait", 1.0),
                )
            nodes.append(node)

        # Special: overlay/popup screens get a close action at the front
        if self._is_overlay(screen_type):
            close_nodes = self._build_close_actions(screen_type)
            nodes = close_nodes + nodes

        return nodes

    def _is_overlay(self, screen_type: str) -> bool:
        """Check if screen is an overlay/popup."""
        overlay_prefixes = ("popup_", "ad", "equipment_detail", "skill_detail", "summon_result")
        return any(screen_type.startswith(p) for p in overlay_prefixes)

    def _build_close_actions(self, screen_type: str) -> List[BTNode]:
        """Build close button tap nodes for overlays."""
        nodes = []
        # Common close positions (top-right X, bottom confirm)
        close_positions = [
            (978, 165, "close_x_topright"),
            (540, 1870, "close_confirm_bottom"),
            (60, 80, "close_back_topleft"),
        ]

        # From nav graph: edges with "close" or "back" elements
        if self._graph:
            edges = self._graph.get_edges_from(screen_type)
            for edge in edges:
                elem = getattr(edge.action, "element", "")
                if "close" in elem.lower() or "back" in elem.lower():
                    nodes.append(TapAction(
                        name=f"close:{elem}",
                        x=edge.action.x, y=edge.action.y,
                    ))

        # Fallback close positions
        for x, y, name in close_positions:
            nodes.append(TapAction(name=f"close:{name}", x=x, y=y))

        return nodes
