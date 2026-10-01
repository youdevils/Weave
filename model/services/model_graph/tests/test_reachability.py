from django.test import SimpleTestCase

from model.services.model_graph.reachability import reachable_within


class ReachableWithinTests(SimpleTestCase):

    def test_depth_zero_returns_only_roots(self):
        adjacency = {"a": ["b"], "b": ["a", "c"]}

        self.assertEqual(reachable_within(["a"], adjacency, 0), {"a"})

    def test_unlimited_depth_walks_whole_component(self):
        adjacency = {"a": ["b"], "b": ["a", "c"], "c": ["b"]}

        self.assertEqual(reachable_within(["a"], adjacency, None), {"a", "b", "c"})

    def test_bounded_depth_stops_at_the_configured_number_of_hops(self):
        adjacency = {"a": ["b"], "b": ["a", "c"], "c": ["b", "d"], "d": ["c"]}

        self.assertEqual(reachable_within(["a"], adjacency, 2), {"a", "b", "c"})

    def test_disconnected_nodes_not_reached(self):
        adjacency = {"a": ["b"], "b": ["a"], "c": ["d"], "d": ["c"]}

        self.assertEqual(reachable_within(["a"], adjacency, None), {"a", "b"})

    def test_handles_cycles_without_infinite_loop(self):
        adjacency = {"a": ["b"], "b": ["c"], "c": ["a"]}

        self.assertEqual(reachable_within(["a"], adjacency, None), {"a", "b", "c"})

    def test_multiple_roots_are_all_seeded(self):
        adjacency = {"a": [], "b": [], "c": ["d"], "d": ["c"]}

        self.assertEqual(reachable_within(["a", "c"], adjacency, None), {"a", "c", "d"})

    def test_unknown_root_with_no_adjacency_entry_is_still_included(self):
        self.assertEqual(reachable_within(["lonely"], {}, None), {"lonely"})
