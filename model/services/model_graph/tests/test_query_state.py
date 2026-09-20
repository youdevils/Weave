from django.test import SimpleTestCase

from model.services.model_graph.query import DEFAULT_LIMIT, ExplorerQuery, QueryError, parse_filter_entries

from .builders import APP, MEMBER_OF, OPS, PERSON, TEAM, sample_dataset, uid


class FromStateTests(SimpleTestCase):
    """``from_state`` accepts the document the Explorer client holds and sanitises it like ``from_params``."""

    def test_empty_or_non_dict_state_is_the_default_query(self):
        for state in (None, {}, [], "nope"):
            with self.subTest(state=state):
                query, dropped = ExplorerQuery.from_state(state, sample_dataset())
                self.assertEqual(query, ExplorerQuery())
                self.assertEqual(dropped, [])

    def test_state_and_params_agree(self):
        filters = [{"type_id": uid(APP), "key": "status", "op": "in", "value": ["Live"]}]
        from_state, _ = ExplorerQuery.from_state(
            {
                "hiddenObjectTypes": [uid(TEAM)],
                "hiddenRelationshipTypes": [uid(MEMBER_OF)],
                "include": [uid(OPS)],
                "attributeFilters": filters,
                "limit": 5,
            },
            sample_dataset(),
        )
        import json

        from_params, _ = ExplorerQuery.from_params(
            {
                "hide_objects": [uid(TEAM)],
                "hide_relationships": [uid(MEMBER_OF)],
                "include": [uid(OPS)],
                "filters": json.dumps(filters),
                "limit": 5,
            },
            sample_dataset(),
        )

        self.assertEqual(from_state, from_params)

    def test_stale_entries_are_dropped_and_reported(self):
        query, dropped = ExplorerQuery.from_state(
            {
                "hiddenObjectTypes": [uid(999), uid(TEAM)],
                "include": ["not-a-uuid"],
                "attributeFilters": [{"type_id": uid(PERSON), "key": "gone", "op": "contains", "value": "x"}],
            },
            sample_dataset(),
        )

        self.assertEqual(query.hidden_object_types, {uid(TEAM)})
        self.assertEqual(query.include, frozenset())
        self.assertEqual(query.attribute_filters, ())
        self.assertEqual({d["kind"] for d in dropped}, {"object_type", "object", "attribute_filter"})

    def test_a_malformed_filter_list_is_an_error(self):
        with self.assertRaises(QueryError):
            ExplorerQuery.from_state({"attributeFilters": "nope"}, sample_dataset())

    def test_limit_is_clamped_like_params(self):
        self.assertEqual(ExplorerQuery.from_state({"limit": 0}, sample_dataset())[0].limit, 1)
        self.assertEqual(ExplorerQuery.from_state({"limit": 99999}, sample_dataset())[0].limit, 1000)
        self.assertEqual(ExplorerQuery.from_state({"limit": "x"}, sample_dataset())[0].limit, DEFAULT_LIMIT)


class ParseFilterEntriesTests(SimpleTestCase):

    def test_duplicates_collapse_and_invalid_entries_are_reported(self):
        entry = {"type_id": uid(APP), "key": "owner", "op": "contains", "value": "car"}
        dropped = []

        parsed = parse_filter_entries([entry, dict(entry), "nonsense", {"type_id": uid(APP), "key": "nope"}], sample_dataset(), dropped)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(dropped), 2)
