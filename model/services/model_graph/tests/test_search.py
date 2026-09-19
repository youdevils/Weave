from django.test import SimpleTestCase

from model.services.model_graph.dataset import EffectiveDataset
from model.services.model_graph.projection import project
from model.services.model_graph.query import ExplorerQuery
from model.services.model_graph.search import search_objects, searchable_fields

from .builders import (
    ALICE,
    ALICE_TWO,
    APP,
    PERSON,
    TEAM,
    WEB,
    object_type,
    obj,
    sample_dataset,
    spec,
    uid,
)


def ids(results):
    return [r["id"] for r in results.results]


class SearchMatchingTests(SimpleTestCase):

    def setUp(self):
        self.dataset = sample_dataset()

    def test_case_insensitive(self):
        self.assertEqual(ids(search_objects(self.dataset, "WEB PORTAL")), [uid(WEB)])

    def test_partial_match(self):
        self.assertEqual(ids(search_objects(self.dataset, "ortal")), [uid(WEB)])

    def test_whitespace_is_normalised(self):
        self.assertEqual(ids(search_objects(self.dataset, "  web    portal ")), [uid(WEB)])

    def test_matches_populated_attribute_values(self):
        results = search_objects(self.dataset, "carol")

        self.assertEqual(ids(results), [uid(WEB)])
        self.assertEqual(results.results[0]["match"], {"field": "Owner", "snippet": "Carol"})

    def test_name_matches_have_no_attribute_match_detail(self):
        self.assertIsNone(search_objects(self.dataset, "web").results[0]["match"])

    def test_matches_email_style_attributes(self):
        self.assertEqual(sorted(ids(search_objects(self.dataset, "example.com"))), sorted([uid(ALICE), uid(ALICE_TWO)]))

    def test_booleans_and_empty_values_are_not_searchable(self):
        self.assertEqual(search_objects(self.dataset, "true").total, 0)
        self.assertEqual(search_objects(self.dataset, "none").total, 0)

    def test_no_results(self):
        results = search_objects(self.dataset, "zzz-nothing")

        self.assertEqual((results.total, results.results), (0, ()))
        self.assertFalse(results.truncated)

    def test_empty_and_blank_queries_return_nothing(self):
        for query in ("", "   ", None):
            results = search_objects(self.dataset, query)
            self.assertEqual((results.total, results.results), (0, ()))


class SearchRankingTests(SimpleTestCase):

    def test_exact_before_prefix_before_contains_before_attribute(self):
        dataset = EffectiveDataset(
            [object_type(APP, "Application", [spec("owner")])],
            [],
            [
                obj(1, APP, "Portal Gateway"),  # prefix
                obj(2, APP, "The Portal"),  # contains
                obj(3, APP, "Portal"),  # exact
                obj(4, APP, "Zed", {"owner": "portal team"}),  # attribute
            ],
            [],
        )

        self.assertEqual(ids(search_objects(dataset, "portal")), [uid(3), uid(1), uid(2), uid(4)])

    def test_name_match_outranks_attribute_match_on_the_same_object(self):
        dataset = EffectiveDataset(
            [object_type(APP, "Application", [spec("owner")])],
            [],
            [obj(1, APP, "Alpha", {"owner": "Alpha"})],
            [],
        )

        self.assertIsNone(search_objects(dataset, "alpha").results[0]["match"])


class SearchDuplicateAndLimitTests(SimpleTestCase):

    def test_duplicate_names_are_returned_separately_and_distinguishable(self):
        results = search_objects(sample_dataset(), "alice")

        self.assertEqual(results.total, 2)
        first, second = results.results
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["name"], second["name"])
        self.assertNotEqual(first["subtitle"], second["subtitle"])  # email differs
        self.assertEqual(first["typeName"], "Person")
        self.assertEqual(first["connections"], 1)

    def test_large_result_sets_are_capped_with_a_total(self):
        many = [obj(1000 + n, PERSON, f"Person {n:04d}") for n in range(120)]
        dataset = EffectiveDataset([object_type(PERSON, "Person")], [], many, [])

        results = search_objects(dataset, "person", limit=25)

        self.assertEqual(len(results.results), 25)
        self.assertEqual(results.total, 120)
        self.assertTrue(results.truncated)
        self.assertEqual(results.to_dict()["truncated"], True)

    def test_snippets_are_bounded(self):
        dataset = EffectiveDataset(
            [object_type(APP, "Application", [spec("notes")])],
            [],
            [obj(1, APP, "X", {"notes": "needle " + "x" * 500})],
            [],
        )

        snippet = search_objects(dataset, "needle").results[0]["match"]["snippet"]

        self.assertLessEqual(len(snippet), 80)

    def test_result_order_is_deterministic(self):
        dataset = sample_dataset()

        self.assertEqual(ids(search_objects(dataset, "a")), ids(search_objects(dataset, "a")))


class SearchViewStateTests(SimpleTestCase):

    def test_results_outside_the_current_filter_are_reported_not_in_view(self):
        dataset = sample_dataset()
        query, _ = ExplorerQuery.from_params({"hide_objects": [uid(APP)]}, dataset)
        projection = project(dataset, query)

        result = search_objects(dataset, "web", projection=projection).results[0]

        self.assertIs(result["inView"], False)

    def test_results_inside_the_view_are_flagged(self):
        dataset = sample_dataset()
        projection = project(dataset, ExplorerQuery.from_params({}, dataset)[0])

        self.assertIs(search_objects(dataset, "web", projection=projection).results[0]["inView"], True)

    def test_in_view_is_unknown_without_a_projection(self):
        self.assertIsNone(search_objects(sample_dataset(), "web").results[0]["inView"])

    def test_search_does_not_change_the_dataset(self):
        dataset = sample_dataset()
        before = (dict(dataset.objects), dict(dataset.relationships))

        search_objects(dataset, "alice")

        self.assertEqual((dict(dataset.objects), dict(dataset.relationships)), before)


class SearchableFieldsHookTests(SimpleTestCase):

    def test_name_is_first_then_populated_non_boolean_attributes(self):
        dataset = sample_dataset()
        web = dataset.object(uid(WEB))

        fields = searchable_fields(web, dataset.object_types[web.type_id])

        self.assertEqual(fields[0], ("Name", "Web Portal"))
        labels = [label for label, _ in fields]
        self.assertIn("Owner", labels)
        self.assertNotIn("Critical", labels)
