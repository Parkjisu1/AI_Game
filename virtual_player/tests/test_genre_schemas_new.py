"""Tests for new genre schemas (tycoon, simulation, casual) and registry."""

import unittest

from virtual_player.genre.schema import GenreSchema


class TestTycoonSchema(unittest.TestCase):
    """Test TycoonSchema implementation."""

    def setUp(self):
        from virtual_player.genre.tycoon_schema import TycoonSchema
        self.schema = TycoonSchema()

    def test_genre_key(self):
        self.assertEqual(self.schema.genre_key, "tycoon")

    def test_genre_name(self):
        self.assertEqual(self.schema.genre_name, "Tycoon")

    def test_concepts_not_empty(self):
        concepts = self.schema.get_concepts()
        self.assertGreater(len(concepts), 0)

    def test_has_required_concepts(self):
        concepts = self.schema.get_concepts()
        required = [k for k, v in concepts.items() if v.is_required]
        self.assertGreater(len(required), 0)

    def test_screen_types_not_empty(self):
        types = self.schema.get_screen_types()
        self.assertGreater(len(types), 0)

    def test_screen_rois_provided(self):
        rois = self.schema.get_default_screen_rois()
        self.assertIsInstance(rois, dict)

    def test_goal_templates(self):
        goals = self.schema.get_goal_templates()
        self.assertIsInstance(goals, list)

    def test_action_templates(self):
        actions = self.schema.get_action_templates()
        self.assertIsInstance(actions, list)

    def test_interrupt_rules(self):
        rules = self.schema.get_interrupt_rules()
        self.assertIsInstance(rules, list)

    def test_is_genre_schema(self):
        self.assertIsInstance(self.schema, GenreSchema)


class TestSimulationSchema(unittest.TestCase):
    """Test SimulationSchema implementation."""

    def setUp(self):
        from virtual_player.genre.simulation_schema import SimulationSchema
        self.schema = SimulationSchema()

    def test_genre_key(self):
        self.assertEqual(self.schema.genre_key, "simulation")

    def test_genre_name(self):
        self.assertEqual(self.schema.genre_name, "Simulation")

    def test_concepts_not_empty(self):
        concepts = self.schema.get_concepts()
        self.assertGreater(len(concepts), 0)

    def test_has_required_concepts(self):
        concepts = self.schema.get_concepts()
        required = [k for k, v in concepts.items() if v.is_required]
        self.assertGreater(len(required), 0)

    def test_screen_types(self):
        types = self.schema.get_screen_types()
        self.assertGreater(len(types), 0)

    def test_goal_templates(self):
        self.assertIsInstance(self.schema.get_goal_templates(), list)

    def test_action_templates(self):
        self.assertIsInstance(self.schema.get_action_templates(), list)

    def test_interrupt_rules(self):
        self.assertIsInstance(self.schema.get_interrupt_rules(), list)


class TestCasualSchema(unittest.TestCase):
    """Test CasualSchema implementation."""

    def setUp(self):
        from virtual_player.genre.casual_schema import CasualSchema
        self.schema = CasualSchema()

    def test_genre_key(self):
        self.assertEqual(self.schema.genre_key, "casual")

    def test_genre_name(self):
        self.assertEqual(self.schema.genre_name, "Casual")

    def test_concepts_not_empty(self):
        concepts = self.schema.get_concepts()
        self.assertGreater(len(concepts), 0)

    def test_has_lives_concept(self):
        concepts = self.schema.get_concepts()
        self.assertIn("lives", concepts)

    def test_screen_types_includes_gameplay(self):
        types = self.schema.get_screen_types()
        self.assertIn("gameplay", types)

    def test_exploration_hints(self):
        hints = self.schema.get_exploration_hints()
        self.assertIsInstance(hints, dict)
        self.assertIn("priority_screens", hints)


class TestSchemaRegistry(unittest.TestCase):
    """Test get_schema_for_genre covers all 8 genres."""

    def test_all_genres_registered(self):
        from virtual_player.genre.game_profile import get_schema_for_genre
        genres = ["rpg", "idle", "merge", "slg", "puzzle", "tycoon", "simulation", "casual"]
        for genre in genres:
            schema = get_schema_for_genre(genre)
            self.assertIsNotNone(schema, f"Schema missing for genre: {genre}")
            self.assertEqual(schema.genre_key, genre)

    def test_unknown_genre_returns_none(self):
        from virtual_player.genre.game_profile import get_schema_for_genre
        self.assertIsNone(get_schema_for_genre("nonexistent"))

    def test_case_insensitive(self):
        from virtual_player.genre.game_profile import get_schema_for_genre
        self.assertIsNotNone(get_schema_for_genre("RPG"))
        self.assertIsNotNone(get_schema_for_genre("Idle"))

    def test_all_schemas_implement_abstract(self):
        """Every registered schema must implement all abstract methods."""
        from virtual_player.genre.game_profile import get_schema_for_genre
        genres = ["rpg", "idle", "merge", "slg", "puzzle", "tycoon", "simulation", "casual"]
        for genre in genres:
            schema = get_schema_for_genre(genre)
            self.assertIsNotNone(schema)
            # Call every abstract method -- should not raise
            schema.get_concepts()
            schema.get_default_screen_rois()
            schema.get_goal_templates()
            schema.get_action_templates()
            schema.get_interrupt_rules()


if __name__ == "__main__":
    unittest.main()
