"""Tests for ScreenActionResolver + ActivityScheduler."""

import unittest
from typing import Dict, List, Tuple
from unittest.mock import MagicMock


def _make_mock_nav_graph(
    nodes: Dict[str, Dict] = None,
    edges: List[Dict] = None,
) -> MagicMock:
    """Build a mock NavigationGraph with specified nodes and edges."""
    graph = MagicMock()

    # Build node data
    node_data = {}
    if nodes:
        for screen_type, info in nodes.items():
            node = MagicMock()
            node.screen_type = screen_type
            node.elements = info.get("elements", [])
            node.in_screen_actions = info.get("in_screen_actions", [])
            node_data[screen_type] = node

    graph.nodes = node_data

    # get_in_screen_actions returns actions from node
    def get_in_screen_actions(screen_type):
        node = node_data.get(screen_type)
        if node:
            return list(node.in_screen_actions)
        return []
    graph.get_in_screen_actions = get_in_screen_actions

    # Build edges
    edge_list = []
    if edges:
        for e in edges:
            edge = MagicMock()
            edge.source = e["source"]
            edge.target = e["target"]
            edge.success_count = e.get("success_count", 1)
            action = MagicMock()
            action.action_type = e.get("action_type", "tap")
            action.x = e.get("x", 540)
            action.y = e.get("y", 960)
            action.x2 = e.get("x2", 0)
            action.y2 = e.get("y2", 0)
            action.element = e.get("element", "")
            edge.action = action
            edge_list.append(edge)

    # get_edges_from returns edges from source, sorted by success_count desc
    def get_edges_from(screen_type):
        result = [e for e in edge_list if e.source == screen_type]
        result.sort(key=lambda e: e.success_count, reverse=True)
        return result
    graph.get_edges_from = get_edges_from

    return graph


class TestScreenActionResolver(unittest.TestCase):
    """Test ScreenActionResolver."""

    def setUp(self):
        self._tap_log: List[Tuple[int, int]] = []

    def _tap(self, x: int, y: int, wait: float = 0.0):
        self._tap_log.append((x, y))

    def _make_resolver(self, nodes=None, edges=None):
        from virtual_player.screen_action_resolver import ScreenActionResolver
        graph = _make_mock_nav_graph(nodes=nodes, edges=edges)
        return ScreenActionResolver(nav_graph=graph, tap_fn=self._tap)

    def test_resolve_picks_interaction_skips_idle(self):
        """resolve() should pick interaction/scroll actions, skip idle."""
        nodes = {
            "lobby": {
                "elements": ["shop_button", "empty_area"],
                "in_screen_actions": [
                    {"action_type": "tap", "x": 100, "y": 200, "element": "empty_area",
                     "category": "idle", "description": "no change"},
                    {"action_type": "tap", "x": 300, "y": 400, "element": "shop_button",
                     "category": "interaction", "description": "open shop"},
                    {"action_type": "swipe", "x": 500, "y": 600, "x2": 500, "y2": 300,
                     "element": "item_list", "category": "scroll", "description": "scroll items"},
                ],
            },
        }
        resolver = self._make_resolver(nodes=nodes)

        result1 = resolver.resolve("lobby")
        self.assertIsNotNone(result1)
        self.assertIn("shop_button", result1)
        # Should tap at (300, 400), not the idle action
        self.assertEqual(self._tap_log[-1], (300, 400))

        result2 = resolver.resolve("lobby")
        self.assertIsNotNone(result2)
        self.assertIn("item_list", result2)

    def test_resolve_returns_none_when_no_actions(self):
        """resolve() returns None for screens with no usable actions."""
        nodes = {"popup_reward": {"elements": [], "in_screen_actions": []}}
        resolver = self._make_resolver(nodes=nodes)
        self.assertIsNone(resolver.resolve("popup_reward"))

    def test_round_robin_exhaustion(self):
        """After all actions are used, resolve() returns None."""
        nodes = {
            "lobby": {
                "elements": ["btn"],
                "in_screen_actions": [
                    {"action_type": "tap", "x": 100, "y": 200, "element": "btn",
                     "category": "interaction", "description": "click"},
                ],
            },
        }
        resolver = self._make_resolver(nodes=nodes)

        result1 = resolver.resolve("lobby")
        self.assertIsNotNone(result1)

        result2 = resolver.resolve("lobby")
        self.assertIsNone(result2)

    def test_reset_on_screen_change(self):
        """Round-robin resets when screen changes."""
        nodes = {
            "lobby": {
                "elements": ["btn"],
                "in_screen_actions": [
                    {"action_type": "tap", "x": 100, "y": 200, "element": "btn",
                     "category": "interaction", "description": "click"},
                ],
            },
            "battle": {
                "elements": ["skill"],
                "in_screen_actions": [
                    {"action_type": "tap", "x": 300, "y": 400, "element": "skill",
                     "category": "interaction", "description": "use skill"},
                ],
            },
        }
        resolver = self._make_resolver(nodes=nodes)

        # Use lobby action
        self.assertIsNotNone(resolver.resolve("lobby"))
        self.assertIsNone(resolver.resolve("lobby"))

        # Switch to battle
        self.assertIsNotNone(resolver.resolve("battle"))

        # Back to lobby -- should reset
        self.assertIsNotNone(resolver.resolve("lobby"))

    def test_is_closeable(self):
        """is_closeable detects popup/overlay/detail screens."""
        nodes = {
            "popup_reward": {"elements": [], "in_screen_actions": []},
            "equipment_detail": {"elements": ["close_button"], "in_screen_actions": []},
            "lobby": {"elements": ["shop_button"], "in_screen_actions": []},
            "menu_inventory": {"elements": ["close_button"], "in_screen_actions": []},
        }
        resolver = self._make_resolver(nodes=nodes)

        self.assertTrue(resolver.is_closeable("popup_reward"))
        self.assertTrue(resolver.is_closeable("equipment_detail"))
        self.assertTrue(resolver.is_closeable("menu_inventory"))  # has close_button element
        self.assertFalse(resolver.is_closeable("lobby"))

    def test_close_overlay_uses_nav_edges(self):
        """close_overlay uses nav edges with close_button element first."""
        nodes = {
            "equipment_detail": {"elements": ["close_button"], "in_screen_actions": []},
            "lobby": {"elements": [], "in_screen_actions": []},
        }
        edges = [
            {"source": "equipment_detail", "target": "lobby",
             "element": "close_button", "x": 1020, "y": 80},
        ]
        resolver = self._make_resolver(nodes=nodes, edges=edges)
        result = resolver.close_overlay("equipment_detail")
        self.assertTrue(result)
        self.assertEqual(self._tap_log[-1], (1020, 80))

    def test_close_overlay_fallback(self):
        """close_overlay falls back to (540,1870) when no edges/close buttons."""
        nodes = {"popup_unknown": {"elements": [], "in_screen_actions": []}}
        resolver = self._make_resolver(nodes=nodes)
        result = resolver.close_overlay("popup_unknown")
        self.assertTrue(result)
        self.assertEqual(self._tap_log[-1], (540, 1870))

    def test_transition_target_picks_highest_success(self):
        """get_transition_target picks edge with highest success_count."""
        nodes = {
            "menu_shop": {"elements": [], "in_screen_actions": []},
            "lobby": {"elements": [], "in_screen_actions": []},
            "battle": {"elements": [], "in_screen_actions": []},
        }
        edges = [
            {"source": "menu_shop", "target": "lobby", "success_count": 5},
            {"source": "menu_shop", "target": "battle", "success_count": 2},
        ]
        resolver = self._make_resolver(nodes=nodes, edges=edges)
        target = resolver.get_transition_target("menu_shop")
        self.assertEqual(target, "lobby")

    def test_transition_target_returns_none_no_edges(self):
        """get_transition_target returns None when no outgoing edges."""
        nodes = {"isolated": {"elements": [], "in_screen_actions": []}}
        resolver = self._make_resolver(nodes=nodes)
        self.assertIsNone(resolver.get_transition_target("isolated"))


class TestActivityScheduler(unittest.TestCase):
    """Test ActivityScheduler."""

    def _make_scheduler(self, **kwargs):
        from virtual_player.screen_action_resolver import ActivityScheduler
        return ActivityScheduler(**kwargs)

    def test_battle_to_lobby_after_dwell(self):
        """After battle_dwell ticks in battle, scheduler returns 'lobby'."""
        scheduler = self._make_scheduler(battle_dwell=5, lobby_dwell=3, force_town_interval=100)

        for _ in range(4):
            result = scheduler.tick("battle")
            self.assertIsNone(result)

        result = scheduler.tick("battle")
        self.assertEqual(result, "lobby")

    def test_lobby_to_battle_after_dwell(self):
        """After lobby_dwell ticks in lobby, scheduler returns 'battle'."""
        scheduler = self._make_scheduler(battle_dwell=10, lobby_dwell=3, force_town_interval=100)

        for _ in range(2):
            result = scheduler.tick("lobby")
            self.assertIsNone(result)

        result = scheduler.tick("lobby")
        self.assertEqual(result, "battle")

    def test_menu_returns_to_lobby(self):
        """Menu screens return to lobby after menu_dwell ticks."""
        scheduler = self._make_scheduler(menu_dwell=2, force_town_interval=100)

        result = scheduler.tick("menu_shop")
        self.assertIsNone(result)

        result = scheduler.tick("menu_shop")
        self.assertEqual(result, "lobby")

    def test_forced_town_visit(self):
        """Every force_town_interval ticks, forces a lobby visit."""
        scheduler = self._make_scheduler(
            battle_dwell=100,  # Won't trigger naturally
            force_town_interval=5,
        )

        for _ in range(4):
            scheduler.tick("battle")

        result = scheduler.tick("battle")
        self.assertEqual(result, "lobby")

    def test_no_forced_visit_when_already_in_lobby(self):
        """No forced visit if already in lobby."""
        scheduler = self._make_scheduler(
            lobby_dwell=100,
            force_town_interval=5,
        )

        for _ in range(5):
            result = scheduler.tick("lobby")

        # At tick 5 (force_town_interval), already in lobby -> no redirect
        self.assertIsNone(result)

    def test_screen_change_resets_dwell(self):
        """Dwell counter resets when screen changes."""
        scheduler = self._make_scheduler(battle_dwell=3, lobby_dwell=3, force_town_interval=100)

        # 2 ticks in battle
        scheduler.tick("battle")
        scheduler.tick("battle")

        # Switch to lobby, then back to battle -- counter resets
        scheduler.tick("lobby")
        result = scheduler.tick("battle")
        self.assertIsNone(result)  # Only 1 tick in battle now

        result = scheduler.tick("battle")
        self.assertIsNone(result)  # 2 ticks

        result = scheduler.tick("battle")
        self.assertEqual(result, "lobby")  # 3 ticks -> trigger

    def test_reset_clears_state(self):
        """reset() clears all scheduler state."""
        scheduler = self._make_scheduler(battle_dwell=3, force_town_interval=100)

        scheduler.tick("battle")
        scheduler.tick("battle")
        scheduler.reset()

        # After reset, counter restarts
        result = scheduler.tick("battle")
        self.assertIsNone(result)  # Only 1 tick


class TestWorldStateFromDict(unittest.TestCase):
    """Test that WorldState.from_snapshot handles dict input (Step 1 fix)."""

    def test_from_dict(self):
        from virtual_player.reasoning.goap_planner import WorldState
        snapshot = {"screen_type": "battle", "gold": 1500, "hp_pct": 0.8}
        ws = WorldState.from_snapshot(snapshot)
        self.assertEqual(ws.props["screen_type"], "battle")
        self.assertEqual(ws.props["gold"], 1500)
        self.assertEqual(ws.props["hp_pct"], 0.8)

    def test_from_dict_empty(self):
        from virtual_player.reasoning.goap_planner import WorldState
        ws = WorldState.from_snapshot({})
        self.assertEqual(ws.props, {})

    def test_satisfies_after_from_dict(self):
        from virtual_player.reasoning.goap_planner import WorldState
        ws = WorldState.from_snapshot({"gold": 2000, "screen_type": "lobby"})
        self.assertTrue(ws.satisfies({"screen_type": "lobby"}))
        self.assertTrue(ws.satisfies({"gold": lambda g: g >= 1000}))


class TestEnrichActionsFromNavGraph(unittest.TestCase):
    """Test enrich_actions_from_nav_graph."""

    def test_enriches_survival_actions(self):
        from virtual_player.reasoning.goap_planner import GOAPAction
        from virtual_player.reasoning.goal_library import enrich_actions_from_nav_graph

        action = GOAPAction(
            name="buy_potion",
            cost=2.0,
            required_screen="menu_shop",
            metadata={"category": "survival"},
        )

        graph = _make_mock_nav_graph(
            nodes={
                "menu_shop": {
                    "elements": ["item_potion_large"],
                    "in_screen_actions": [
                        {"action_type": "tap", "x": 371, "y": 321,
                         "element": "item_potion_large", "category": "interaction"},
                    ],
                },
            },
        )

        count = enrich_actions_from_nav_graph([action], graph)
        self.assertEqual(count, 1)
        self.assertEqual(action.metadata["tap_x"], 371)
        self.assertEqual(action.metadata["tap_y"], 321)

    def test_skips_already_enriched(self):
        from virtual_player.reasoning.goap_planner import GOAPAction
        from virtual_player.reasoning.goal_library import enrich_actions_from_nav_graph

        action = GOAPAction(
            name="buy_potion",
            metadata={"category": "survival", "tap_x": 100, "tap_y": 200},
        )
        graph = _make_mock_nav_graph(
            nodes={"menu_shop": {"elements": [], "in_screen_actions": [
                {"action_type": "tap", "x": 999, "y": 999,
                 "element": "potion", "category": "interaction"},
            ]}},
        )
        count = enrich_actions_from_nav_graph([action], graph)
        self.assertEqual(count, 0)
        self.assertEqual(action.metadata["tap_x"], 100)  # unchanged

    def test_no_match_leaves_action_unenriched(self):
        from virtual_player.reasoning.goap_planner import GOAPAction
        from virtual_player.reasoning.goal_library import enrich_actions_from_nav_graph

        action = GOAPAction(
            name="unknown_action",
            metadata={"category": "unknown_category"},
        )
        graph = _make_mock_nav_graph(nodes={"lobby": {"elements": [], "in_screen_actions": []}})
        count = enrich_actions_from_nav_graph([action], graph)
        self.assertEqual(count, 0)
        self.assertNotIn("tap_x", action.metadata)


if __name__ == "__main__":
    unittest.main()
