import json

from django.http import QueryDict
from django.test import SimpleTestCase

from model.services.model_graph.query import DEFAULT_LIMIT, MAX_LIMIT, ExplorerQuery, QueryError

from .builders import APP, MEMBER_OF, OPS, PERSON, TEAM, WEB, sample_dataset, uid


def parse(dataset=None, **params):
    dataset = dataset or sample_dataset()
    return ExplorerQuery.from_params({k: v for k, v in params.items()}, dataset)


class IdParameterTests(SimpleTestCase):

    def test_empty_params_give_the_default_unfiltered_query(self):
        query, dropped = parse()

        self.assertEqual(query.hidden_object_types, frozenset())
        self.assertEqual(query.attribute_filters, ())
        self.assertEqual(query.limit, DEFAULT_LIMIT)
        self.assertEqual(dropped, [])

    def test_known_ids_are_kept_and_deduplicated(self):
        query, dropped = parse(
            hide_objects=[uid(TEAM), uid(TEAM)],
            hide_relationships=[uid(MEMBER_OF)],
            include=[uid(OPS)],
        )

        self.assertEqual(query.hidden_object_types, {uid(TEAM)})
        self.assertEqual(query.hidden_relationship_types, {uid(MEMBER_OF)})
        self.assertEqual(query.include, {uid(OPS)})
        self.assertEqual(dropped, [])

    def test_stale_and_invalid_ids_are_dropped_and_reported(self):
        query, dropped = parse(
            hide_objects=[uid(999), "not-a-uuid"],
            hide_relationships=[uid(TEAM)],  # an object type id is not a relationship type
            include=[uid(12345)],
        )

        self.assertEqual(query.hidden_object_types, frozenset())
        self.assertEqual(query.hidden_relationship_types, frozenset())
        self.assertEqual(query.include, frozenset())
        self.assertEqual(len(dropped), 4)
        self.assertEqual({d["reason"] for d in dropped}, {"unknown"})

    def test_uppercase_uuids_are_normalised(self):
        query, _ = parse(hide_objects=[uid(TEAM).upper()])

        self.assertEqual(query.hidden_object_types, {uid(TEAM)})

    def test_works_with_a_django_querydict(self):
        params = QueryDict(f"hide_objects={uid(TEAM)}&hide_objects={uid(APP)}&include={uid(OPS)}")

        query, _ = ExplorerQuery.from_params(params, sample_dataset())

        self.assertEqual(query.hidden_object_types, {uid(TEAM), uid(APP)})

    def test_limit_is_clamped(self):
        self.assertEqual(parse(limit="5")[0].limit, 5)
        self.assertEqual(parse(limit="999999")[0].limit, MAX_LIMIT)
        self.assertEqual(parse(limit="0")[0].limit, 1)
        self.assertEqual(parse(limit="abc")[0].limit, DEFAULT_LIMIT)

    def test_state_echo_round_trips(self):
        query, _ = parse(hide_objects=[uid(TEAM)], include=[uid(OPS)])

        state = query.to_state()

        self.assertEqual(state["hiddenObjectTypes"], [uid(TEAM)])
        self.assertEqual(state["include"], [uid(OPS)])


def filters(*entries):
    return json.dumps(list(entries))


class AttributeFilterParsingTests(SimpleTestCase):

    def test_choice_filter(self):
        query, dropped = parse(
            filters=filters({"type_id": uid(APP), "key": "status", "op": "in", "value": ["Live"]})
        )

        self.assertEqual(dropped, [])
        (attribute_filter,) = query.attribute_filters
        self.assertEqual((attribute_filter.op, attribute_filter.value), ("in", ("Live",)))

    def test_operator_is_derived_from_the_data_type_when_omitted(self):
        query, _ = parse(filters=filters({"type_id": uid(APP), "key": "owner", "value": "car"}))

        self.assertEqual(query.attribute_filters[0].op, "contains")

    def test_wrong_operator_for_the_data_type_is_dropped(self):
        query, dropped = parse(
            filters=filters({"type_id": uid(APP), "key": "owner", "op": "in", "value": ["x"]})
        )

        self.assertEqual(query.attribute_filters, ())
        self.assertEqual(dropped[0]["kind"], "attribute_filter")

    def test_unknown_type_or_attribute_is_dropped(self):
        query, dropped = parse(
            filters=filters(
                {"type_id": uid(999), "key": "status", "value": ["Live"]},
                {"type_id": uid(APP), "key": "nope", "value": "x"},
                {"type_id": uid(APP)},
                "garbage",
            )
        )

        self.assertEqual(query.attribute_filters, ())
        self.assertEqual(len(dropped), 4)

    def test_empty_values_are_dropped(self):
        query, dropped = parse(
            filters=filters(
                {"type_id": uid(APP), "key": "status", "value": []},
                {"type_id": uid(APP), "key": "owner", "value": "   "},
                {"type_id": uid(APP), "key": "users", "value": {}},
                {"type_id": uid(APP), "key": "users", "value": {"min": "", "max": None}},
            )
        )

        self.assertEqual(query.attribute_filters, ())
        self.assertEqual(len(dropped), 4)

    def test_number_range_requires_numeric_bounds(self):
        query, dropped = parse(
            filters=filters(
                {"type_id": uid(APP), "key": "users", "value": {"min": "100", "max": ""}},
                {"type_id": uid(APP), "key": "users", "value": {"min": "abc"}},
            )
        )

        self.assertEqual(query.attribute_filters[0].value, (100.0, None))
        self.assertEqual(len(dropped), 1)

    def test_duplicate_filters_collapse(self):
        entry = {"type_id": uid(APP), "key": "status", "value": ["Live"]}
        query, _ = parse(filters=filters(entry, entry))

        self.assertEqual(len(query.attribute_filters), 1)

    def test_malformed_json_is_an_error(self):
        with self.assertRaises(QueryError):
            parse(filters="{not json")
        with self.assertRaises(QueryError):
            parse(filters=json.dumps({"not": "a list"}))


class AttributeFilterMatchingTests(SimpleTestCase):

    def matcher(self, key, value):
        query, _ = parse(filters=filters({"type_id": uid(APP), "key": key, "value": value}))
        return query.attribute_filters[0]

    def test_in_is_case_insensitive_and_matches_booleans(self):
        self.assertTrue(self.matcher("status", ["live"]).matches("Live"))
        self.assertFalse(self.matcher("status", ["Live"]).matches("Retired"))
        self.assertTrue(self.matcher("critical", ["true"]).matches(True))
        self.assertTrue(self.matcher("critical", ["false"]).matches(False))

    def test_contains_is_partial_and_case_insensitive(self):
        self.assertTrue(self.matcher("owner", "CAR").matches("Carol"))
        self.assertFalse(self.matcher("owner", "zzz").matches("Carol"))

    def test_number_range_bounds_are_inclusive(self):
        between = self.matcher("users", {"min": 40, "max": 100})
        self.assertTrue(between.matches(40))
        self.assertTrue(between.matches(100))
        self.assertFalse(between.matches(101))
        self.assertFalse(between.matches("not a number"))

    def test_open_ended_ranges(self):
        self.assertTrue(self.matcher("users", {"min": 1000}).matches(1200))
        self.assertFalse(self.matcher("users", {"min": 1000}).matches(999))
        self.assertTrue(self.matcher("users", {"max": 50}).matches(40))

    def test_date_range_includes_the_whole_maximum_day(self):
        window = self.matcher("launched", {"min": "2021-01-01", "max": "2021-12-31"})
        self.assertTrue(window.matches("2021-03-01"))
        self.assertTrue(window.matches("2021-12-31T23:59:00Z"))
        self.assertFalse(window.matches("2022-01-01"))
        self.assertFalse(window.matches("2020-12-31"))

    def test_missing_or_blank_values_never_match(self):
        for value in (None, "", "   "):
            self.assertFalse(self.matcher("status", ["Live"]).matches(value))
            self.assertFalse(self.matcher("users", {"min": 0}).matches(value))

    def test_a_stray_number_in_a_date_field_does_not_crash(self):
        self.assertFalse(self.matcher("launched", {"min": "2021-01-01"}).matches(5))
