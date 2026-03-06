"""
Screen Action Resolver + Activity Scheduler
=============================================
Makes the PlayEngine behave like a human player by:

1. ScreenActionResolver: Uses nav_graph in_screen_actions to perform meaningful
   interactions on each screen (tap items, scroll lists, use skills) instead of
   blind grid taps.

2. ActivityScheduler: Rotates between battle, lobby, and menu screens on a
   configurable tick schedule, mimicking a real player's activity pattern.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Screen types that are popups/overlays/detail views (closeable)
_CLOSEABLE_PREFIXES = (
    "popup_", "equipment_detail", "skill_detail", "summon_result",
    "menu_",  # menu screens can be closed back to lobby
)
_HUB_SCREENS = ("lobby", "battle")


class ScreenActionResolver:
    """Resolves what to do on a given screen using nav_graph in_screen_actions.

    Round-robins through interaction and scroll actions (skips idle),
    executing taps/swipes at stored coordinates.
    """

    def __init__(
        self,
        nav_graph: Any,
        tap_fn: Callable[[int, int, float], None],
        swipe_fn: Optional[Callable[[int, int, int, int, float], None]] = None,
    ):
        """
        Args:
            nav_graph: NavigationGraph instance with nodes/edges.
            tap_fn: (x, y, wait) -> None.
            swipe_fn: (x1, y1, x2, y2, wait) -> None. If None, swipes become taps at (x,y).
        """
        self._graph = nav_graph
        self._tap = tap_fn
        self._swipe = swipe_fn
        # Per-screen round-robin index
        self._action_index: Dict[str, int] = {}
        self._last_screen: Optional[str] = None

    def resolve(self, screen_type: str) -> Optional[str]:
        """Pick and execute the next meaningful in-screen action.

        Returns action description string, or None if no actions available.
        """
        actions = self._get_usable_actions(screen_type)
        if not actions:
            return None

        # Reset index on screen change
        if screen_type != self._last_screen:
            self._action_index[screen_type] = 0
            self._last_screen = screen_type

        idx = self._action_index.get(screen_type, 0)
        if idx >= len(actions):
            # Exhausted all actions for this screen, signal None
            return None

        action = actions[idx]
        self._action_index[screen_type] = idx + 1

        # Execute the action
        self._execute_in_screen_action(action)

        element = action.get("element", "unknown")
        category = action.get("category", "unknown")
        desc = action.get("description", "")
        label = f"{category}:{element}"
        logger.info("ScreenActionResolver: %s on '%s' -- %s", label, screen_type, desc[:60])
        return label

    def get_transition_target(self, screen_type: str) -> Optional[str]:
        """Pick the best outgoing edge target (highest success_count).

        Returns target screen_type, or None if no edges.
        """
        edges = self._graph.get_edges_from(screen_type)
        if not edges:
            return None
        # Already sorted by success_count desc in NavigationGraph
        return edges[0].target

    def is_closeable(self, screen_type: str) -> bool:
        """Detect if this is a popup/overlay/detail screen that should be closed."""
        if not screen_type:
            return False
        for prefix in _CLOSEABLE_PREFIXES:
            if screen_type.startswith(prefix):
                return True
        # Also check if graph node has a close_button element
        node = self._graph.nodes.get(screen_type)
        if node:
            for elem in node.elements:
                if "close" in elem.lower():
                    return True
        return False

    def close_overlay(self, screen_type: str) -> bool:
        """Try to close an overlay screen using nav edges or known close patterns.

        Returns True if a close action was attempted.
        """
        # Strategy 1: Find a nav edge from this screen to a non-overlay target
        edges = self._graph.get_edges_from(screen_type)
        for edge in edges:
            action = edge.action
            element = getattr(action, "element", "")
            # Prefer close_button edges
            if "close" in element.lower() or "back" in element.lower():
                self._execute_nav_action(action)
                logger.info("ScreenActionResolver: closed '%s' via edge to '%s'",
                            screen_type, edge.target)
                return True

        # Strategy 2: Look for close_button in in_screen_actions
        node = self._graph.nodes.get(screen_type)
        if node:
            for act in node.in_screen_actions:
                elem = act.get("element", "")
                if "close" in elem.lower() or "back" in elem.lower():
                    self._execute_in_screen_action(act)
                    logger.info("ScreenActionResolver: closed '%s' via in_screen close button",
                                screen_type)
                    return True

        # Strategy 3: Prefer edge to a hub screen (lobby/battle)
        for edge in edges:
            if edge.target in _HUB_SCREENS:
                self._execute_nav_action(edge.action)
                logger.info("ScreenActionResolver: closed '%s' via hub edge to '%s'",
                            screen_type, edge.target)
                return True

        # Strategy 3b: Use any outgoing edge (first available)
        if edges:
            self._execute_nav_action(edges[0].action)
            logger.info("ScreenActionResolver: closed '%s' via first edge to '%s'",
                        screen_type, edges[0].target)
            return True

        # Strategy 4: Fallback positions
        self._tap(540, 1870, 1.0)
        logger.info("ScreenActionResolver: closed '%s' via fallback tap (540,1870)", screen_type)
        return True

    def reset_screen(self, screen_type: str):
        """Reset round-robin index for a screen (e.g., on revisit)."""
        self._action_index[screen_type] = 0

    def _get_usable_actions(self, screen_type: str) -> List[Dict]:
        """Get interaction + scroll actions for this screen (skip idle)."""
        all_actions = self._graph.get_in_screen_actions(screen_type)
        return [
            a for a in all_actions
            if a.get("category") in ("interaction", "scroll")
        ]

    def _execute_in_screen_action(self, action: Dict):
        """Execute an in-screen action dict."""
        action_type = action.get("action_type", "tap")
        x = action.get("x", 540)
        y = action.get("y", 960)

        if action_type == "swipe" and self._swipe:
            x2 = action.get("x2", x)
            y2 = action.get("y2", y)
            self._swipe(x, y, x2, y2, 1.5)
        else:
            self._tap(x, y, 1.0)

    def _execute_nav_action(self, action):
        """Execute a NavAction object."""
        if action.action_type == "swipe" and self._swipe:
            self._swipe(action.x, action.y, action.x2, action.y2, 1.5)
        else:
            self._tap(action.x, action.y, 1.0)


class ActivityScheduler:
    """Rotates between screen types on a tick-based schedule.

    Mimics a human player's activity pattern:
    - Battle for N ticks, then visit town
    - Town for M ticks, then go back to battle
    - Menu screens: short dwell, then return to lobby
    - Periodic forced town visit for shopping/upgrades
    """

    def __init__(
        self,
        nav_graph: Any = None,
        battle_dwell: int = 15,
        lobby_dwell: int = 8,
        menu_dwell: int = 3,
        force_town_interval: int = 30,
    ):
        """
        Args:
            nav_graph: Optional NavigationGraph (for hub detection).
            battle_dwell: Ticks to spend in battle before switching.
            lobby_dwell: Ticks to spend in lobby before switching.
            menu_dwell: Ticks to spend in any menu screen.
            force_town_interval: Every N ticks, force a town/lobby visit.
        """
        self._graph = nav_graph
        self._battle_dwell = battle_dwell
        self._lobby_dwell = lobby_dwell
        self._menu_dwell = menu_dwell
        self._force_town_interval = force_town_interval

        self._tick_count = 0
        self._screen_ticks: Dict[str, int] = {}
        self._last_screen: Optional[str] = None
        self._total_ticks = 0

    def tick(self, screen_type: str) -> Optional[str]:
        """Called each tick with current screen. Returns target screen to navigate to, or None.

        Returns:
            Target screen_type string if it's time to move, None to stay.
        """
        self._total_ticks += 1

        # Track per-screen dwell
        if screen_type != self._last_screen:
            self._screen_ticks[screen_type] = 0
            self._last_screen = screen_type

        self._screen_ticks[screen_type] = self._screen_ticks.get(screen_type, 0) + 1
        dwell = self._screen_ticks[screen_type]

        # Periodic forced town visit
        if (self._total_ticks % self._force_town_interval == 0
                and screen_type != "lobby"):
            logger.info("ActivityScheduler: forced town visit (every %d ticks)",
                        self._force_town_interval)
            return "lobby"

        # Battle screen: dwell then go to lobby
        if screen_type == "battle" and dwell >= self._battle_dwell:
            logger.info("ActivityScheduler: battle->lobby (after %d ticks)", dwell)
            return "lobby"

        # Lobby/town screen: dwell then go to battle
        if screen_type == "lobby" and dwell >= self._lobby_dwell:
            logger.info("ActivityScheduler: lobby->battle (after %d ticks)", dwell)
            return "battle"

        # Menu screens: short dwell then return to lobby
        if screen_type.startswith("menu_") and dwell >= self._menu_dwell:
            logger.info("ActivityScheduler: %s->lobby (after %d ticks)", screen_type, dwell)
            return "lobby"

        return None

    def reset(self):
        """Reset all scheduler state."""
        self._tick_count = 0
        self._screen_ticks.clear()
        self._last_screen = None
        self._total_ticks = 0
