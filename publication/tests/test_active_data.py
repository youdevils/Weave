"""
Publications contain active data only, and type visibility is independent of record activity.

  * inactive objects/relationships never reach the preview, the counts, traversal, filters or the file;
  * an active type is always listed (count 0 when empty); an inactive type is listed only while it
    still has active records;
  * a starting point never turns into stored type exclusions.

Only ``is_active`` is in play here. ``valid_from`` / ``valid_to`` are deliberately not considered.
"""

from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.services.model_graph.facets import build_facets
from publication.services import publishing

from .base import PublicationTestCase


class ActiveDataFixture(PublicationTestCase):
    """alice --member_of--> ops, plus inactive records that must never show up."""

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(self.alice, self.ops)

    def names(self, dataset):
        return sorted(o.name for o in dataset.objects.values())

    def object_type_facets(self):
        return {t["name"]: t for t in build_facets(self.canonical())["objectTypes"]}

    def relationship_type_facets(self):
        return {t["name"]: t for t in build_facets(self.canonical())["relationshipTypes"]}

    def retire(self, *types):
        for retired in types:
            retired.is_active = False
            retired.save()


class InactiveRecordsTests(ActiveDataFixture):

    def test_inactive_records_are_absent_from_the_preview_counts_and_the_file(self):
        ghost = self.make_object(self.person_type, "InactiveGhost", is_active=False)
        self.make_relationship(ghost, self.ops)  # its relationship goes with it
        self.make_relationship(self.alice, self.ops, is_active=False)

        preview = publishing.preview(self.model.id, {})
        html = publishing.publish(
            self.model.id, self.editor, {}, {"revision": preview.revision, "digest": preview.digest}
        ).html

        self.assertEqual(
            (
                preview.summary["objects"],
                preview.summary["relationships"],
                preview.summary["totalObjects"],
                preview.summary["totalRelationships"],
            ),
            (2, 1, 2, 1),
        )
        self.assertNotIn("InactiveGhost", html)

    def test_an_inactive_object_does_not_bridge_a_starting_point_traversal(self):
        bridge = self.make_object(self.team_type, "Bridge", is_active=False)
        carol = self.make_object(self.person_type, "Carol")
        self.make_relationship(self.alice, bridge)
        self.make_relationship(carol, bridge)

        published = self.normalised(
            {"scope": {"traversal": {"roots": [str(self.alice.id)], "depth": None}}}
        ).published

        self.assertEqual(self.names(published), ["Alice", "Ops"])

    def test_an_inactive_object_never_matches_an_object_filter(self):
        self.make_object(self.person_type, "Dormant", attributes={"status": "Active"}, is_active=False)
        status_filter = {"type_id": str(self.person_type.id), "key": "status", "op": "in", "value": ["Active"]}

        published = self.normalised({"scope": {"attribute_filters": [status_filter]}}).published

        self.assertEqual(self.names(published), ["Alice", "Ops"])


class TypeVisibilityTests(ActiveDataFixture):
    """The four rows of the type-selector rule, for object types and relationship types alike."""

    def test_an_active_type_with_no_active_records_is_listed_with_a_zero_count(self):
        ObjectType.objects.create(model=self.model, name="Place", key="place", is_active=True)
        RelationshipType.objects.create(model=self.model, name="Located in", key="located_in", is_active=True)

        self.assertEqual(self.object_type_facets()["Place"]["count"], 0)
        self.assertEqual(self.relationship_type_facets()["Located in"]["count"], 0)

    def test_an_inactive_type_with_active_records_is_still_listed(self):
        self.retire(self.team_type, self.member_of)

        self.assertEqual(self.object_type_facets()["Team"]["count"], 1)
        self.assertEqual(self.relationship_type_facets()["Member of"]["count"], 1)

    def test_an_inactive_type_with_no_active_records_is_omitted(self):
        legacy = ObjectType.objects.create(model=self.model, name="Legacy", key="legacy", is_active=False)
        self.make_object(legacy, "Old thing", is_active=False)
        RelationshipType.objects.create(model=self.model, name="Retired link", key="retired_link", is_active=False)

        self.assertNotIn("Legacy", self.object_type_facets())
        self.assertNotIn("Retired link", self.relationship_type_facets())

    def test_an_inactive_type_whose_only_records_are_inactive_is_omitted(self):
        Relationship.objects.filter(relationship_type=self.member_of).update(is_active=False)
        self.retire(self.member_of)

        self.assertNotIn("Member of", self.relationship_type_facets())

    def test_an_inactive_type_with_active_records_publishes_with_its_records(self):
        self.retire(self.team_type, self.member_of)

        preview = publishing.preview(self.model.id, {})

        self.assertIsNotNone(preview.bundle)  # the appearance of a retired type resolves too
        self.assertEqual((preview.summary["objects"], preview.summary["relationships"]), (2, 1))
        published_types = {t["name"] for t in preview.bundle["facets"]["objectTypes"]}
        self.assertEqual(published_types, {"Person", "Team"})


class StartingPointIsSeparateFromTypeSelectionTests(ActiveDataFixture):

    def test_a_starting_point_is_not_stored_as_type_exclusions(self):
        result = self.normalised({"scope": {"traversal": {"roots": [str(self.alice.id)], "depth": 0}}})

        self.assertEqual(list(result.config.scope.excluded_object_types), [])
        self.assertEqual(list(result.config.scope.excluded_relationship_types), [])
        self.assertEqual(list(result.config.scope.roots), [str(self.alice.id)])

    def test_type_selections_refine_the_starting_point_result_without_dropping_it(self):
        result = self.normalised(
            {
                "scope": {
                    "object_types": {"excluded": [str(self.team_type.id)]},
                    "traversal": {"roots": [str(self.alice.id)], "depth": 1},
                }
            }
        )

        self.assertEqual(list(result.config.scope.roots), [str(self.alice.id)])
        self.assertEqual(list(result.config.scope.excluded_object_types), [str(self.team_type.id)])
        self.assertEqual(self.names(result.published), ["Alice"])

    def test_scoped_facets_count_the_effective_result_and_keep_empty_types_listed(self):
        preview = publishing.preview(
            self.model.id, {"scope": {"traversal": {"roots": [str(self.alice.id)], "depth": 0}}}
        )

        counts = {t["name"]: t["count"] for t in preview.bundle["facets"]["objectTypes"]}
        self.assertEqual(counts, {"Person": 1, "Team": 0})
