from django.test import SimpleTestCase

from model.services.model_graph.projection import project
from model.services.model_graph.query import ExplorerQuery

from .builders import (
    ALICE,
    ALICE_TWO,
    APP,
    BILLING,
    BOB,
    LONER,
    MEMBER_OF,
    OPS,
    PERSON,
    TEAM,
    USES,
    WEB,
    sample_dataset,
    uid,
)


def make_query(dataset, **params):
    query, _ = ExplorerQuery.from_params(params, dataset)
    return query


def names(dataset, projection):
    return sorted(dataset.objects[oid].name for oid in projection.object_ids)


class UnfilteredProjectionTests(SimpleTestCase):

    def test_everything_is_shown_by_default(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset))

        self.assertEqual(len(projection.object_ids), 7)
        self.assertEqual(len(projection.relationship_ids), 4)
        summary = projection.summary
        self.assertEqual((summary.total_objects, summary.shown_objects), (7, 7))
        self.assertFalse(summary.truncated)

    def test_isolated_objects_are_included(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset))

        self.assertIn(uid(LONER), projection.object_ids)

    def test_empty_dataset(self):
        from model.services.model_graph.dataset import EffectiveDataset

        dataset = EffectiveDataset([], [], [], [])
        projection = project(dataset, make_query(dataset))

        self.assertEqual((projection.object_ids, projection.relationship_ids), ((), ()))
        self.assertEqual(projection.summary.shown_objects, 0)


class ObjectTypeFilterTests(SimpleTestCase):

    def test_hiding_an_object_type_hides_its_objects_and_dependent_relationships(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, hide_objects=[uid(TEAM)]))

        self.assertNotIn(uid(OPS), projection.object_ids)
        # Every relationship touched Ops, so none survive.
        self.assertEqual(projection.relationship_ids, ())
        self.assertEqual(projection.summary.hidden_by_object_type, 1)
        self.assertEqual(len(projection.object_ids), 6)

    def test_hiding_a_type_keeps_relationships_between_the_remaining_objects(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, hide_objects=[uid(PERSON)]))

        self.assertEqual(
            sorted(projection.relationship_ids), sorted([uid(1003), uid(1004)])
        )  # Ops -> Web/Billing remain

    def test_clearing_the_filter_restores_the_broader_view(self):
        dataset = sample_dataset()
        narrowed = project(dataset, make_query(dataset, hide_objects=[uid(TEAM), uid(APP)]))
        restored = project(dataset, make_query(dataset))

        self.assertLess(len(narrowed.object_ids), len(restored.object_ids))
        self.assertEqual(len(restored.object_ids), 7)
        self.assertEqual(len(restored.relationship_ids), 4)

    def test_hiding_every_type_yields_an_empty_projection(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, hide_objects=[uid(PERSON), uid(TEAM), uid(APP)]))

        self.assertEqual(projection.object_ids, ())
        self.assertEqual(projection.summary.matching_objects, 0)


class RelationshipTypeFilterTests(SimpleTestCase):

    def test_hiding_a_relationship_type_never_hides_endpoints(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, hide_relationships=[uid(USES)]))

        self.assertEqual(len(projection.object_ids), 7)
        self.assertEqual(sorted(projection.relationship_ids), sorted([uid(1001), uid(1002)]))

    def test_hiding_all_relationship_types_leaves_only_objects(self):
        dataset = sample_dataset()
        projection = project(
            dataset, make_query(dataset, hide_relationships=[uid(USES), uid(MEMBER_OF)])
        )

        self.assertEqual(len(projection.object_ids), 7)
        self.assertEqual(projection.relationship_ids, ())


class AttributeFilterProjectionTests(SimpleTestCase):

    def filter_param(self, **entry):
        import json

        return json.dumps([{"type_id": uid(APP), **entry}])

    def test_filter_constrains_only_its_own_type(self):
        dataset = sample_dataset()
        query = make_query(dataset, filters=self.filter_param(key="status", value=["Live"]))
        projection = project(dataset, query)

        self.assertEqual(names(dataset, projection).count("Billing"), 0)  # Retired app is out
        # Objects of other types are untouched.
        for name in ("Alice", "Bob", "Ops", "Web Portal", "Loner"):
            self.assertIn(name, names(dataset, projection))
        self.assertEqual(projection.summary.hidden_by_attribute_filter, 1)

    def test_relationships_to_filtered_out_objects_are_hidden(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, filters=self.filter_param(key="status", value=["Live"])))

        self.assertNotIn(uid(1004), projection.relationship_ids)  # Ops -> Billing
        self.assertIn(uid(1003), projection.relationship_ids)  # Ops -> Web Portal

    def test_objects_missing_the_attribute_do_not_match(self):
        dataset = sample_dataset()
        # "Loner" has no owner.
        projection = project(dataset, make_query(dataset, filters=self.filter_param(key="owner", value="a")))

        self.assertNotIn("Loner", names(dataset, projection))

    def test_filters_on_one_type_combine_with_and(self):
        dataset = sample_dataset()
        import json

        params = json.dumps(
            [
                {"type_id": uid(APP), "key": "status", "value": ["Live"]},
                {"type_id": uid(APP), "key": "users", "value": {"min": 1000}},
            ]
        )
        projection = project(dataset, make_query(dataset, filters=params))

        apps = [n for n in names(dataset, projection) if n in ("Web Portal", "Billing", "Loner")]
        self.assertEqual(apps, ["Web Portal"])

    def test_zero_result_filter(self):
        dataset = sample_dataset()
        query = make_query(
            dataset, hide_objects=[uid(PERSON), uid(TEAM)], filters=self.filter_param(key="owner", value="nobody")
        )
        projection = project(dataset, query)

        self.assertEqual(projection.object_ids, ())
        self.assertEqual(projection.relationship_ids, ())
        self.assertEqual(projection.summary.shown_objects, 0)
        self.assertEqual(projection.summary.total_objects, 7)


class IncludeTests(SimpleTestCase):

    def test_include_overrides_a_hidden_type(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, hide_objects=[uid(TEAM)], include=[uid(OPS)]))

        self.assertIn(uid(OPS), projection.object_ids)
        self.assertEqual(projection.included_ids, {uid(OPS)})
        # Its relationships return with it.
        self.assertEqual(len(projection.relationship_ids), 4)

    def test_include_overrides_an_attribute_filter(self):
        import json

        dataset = sample_dataset()
        filters = json.dumps([{"type_id": uid(APP), "key": "status", "value": ["Live"]}])
        projection = project(dataset, make_query(dataset, filters=filters, include=[uid(BILLING)]))

        self.assertIn(uid(BILLING), projection.object_ids)
        self.assertIn(uid(1004), projection.relationship_ids)

    def test_relationship_type_hiding_still_applies_to_included_objects(self):
        dataset = sample_dataset()
        projection = project(
            dataset, make_query(dataset, hide_objects=[uid(TEAM)], include=[uid(OPS)], hide_relationships=[uid(USES)])
        )

        self.assertEqual(sorted(projection.relationship_ids), sorted([uid(1001), uid(1002)]))

    def test_including_an_unknown_id_is_ignored(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, include=[uid(424242)]))

        self.assertEqual(projection.summary.included_objects, 0)


class TruncationTests(SimpleTestCase):

    def test_projection_is_bounded_and_says_so(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, limit=3))

        self.assertEqual(len(projection.object_ids), 3)
        self.assertTrue(projection.summary.truncated)
        self.assertEqual(projection.summary.matching_objects, 7)
        self.assertEqual(projection.summary.shown_objects, 3)

    def test_best_connected_objects_are_kept(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, limit=1))

        self.assertEqual(projection.object_ids, (uid(OPS),))  # degree 4

    def test_included_objects_survive_truncation(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, limit=2, include=[uid(LONER)]))

        self.assertIn(uid(LONER), projection.object_ids)
        self.assertEqual(len(projection.object_ids), 2)

    def test_no_dangling_relationships_after_truncation(self):
        dataset = sample_dataset()
        for limit in range(1, 8):
            projection = project(dataset, make_query(dataset, limit=limit))
            kept = set(projection.object_ids)
            for relationship_id in projection.relationship_ids:
                relationship = dataset.relationships[relationship_id]
                self.assertIn(relationship.source_id, kept)
                self.assertIn(relationship.target_id, kept)

    def test_not_truncated_at_exactly_the_limit(self):
        dataset = sample_dataset()

        self.assertFalse(project(dataset, make_query(dataset, limit=7)).summary.truncated)

    def test_truncation_is_deterministic(self):
        dataset = sample_dataset()
        query = make_query(dataset, limit=4)

        self.assertEqual(project(dataset, query).object_ids, project(dataset, query).object_ids)


class ProjectionStateTests(SimpleTestCase):

    def test_duplicate_named_objects_are_distinct_members(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset))

        self.assertIn(uid(ALICE), projection.object_ids)
        self.assertIn(uid(ALICE_TWO), projection.object_ids)

    def test_membership_helpers(self):
        dataset = sample_dataset()
        projection = project(dataset, make_query(dataset, hide_objects=[uid(TEAM)]))

        self.assertTrue(projection.contains_object(uid(ALICE)))
        self.assertFalse(projection.contains_object(uid(OPS)))
        self.assertFalse(projection.contains_relationship(uid(1001)))
