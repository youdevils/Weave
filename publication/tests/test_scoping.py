from model.models.attribute_definition import AttributeDefinition
from model.models.object import Object
from publication.services.config import PublicationScope, sanitise_scope
from publication.services.scoping import apply_scope

from .base import PublicationTestCase


class ScopeFixture(PublicationTestCase):
    """
    alice --member_of--> ops <--member_of-- bob        carol --member_of--> dev
    (Person: status Active/Left)                        (a separate component)
    """

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.bob = self.make_object(self.person_type, "Bob", attributes={"status": "Left"})
        self.carol = self.make_object(self.person_type, "Carol", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.dev = self.make_object(self.team_type, "Dev")
        self.r_alice = self.make_relationship(self.alice, self.ops)
        self.r_bob = self.make_relationship(self.bob, self.ops)
        self.r_carol = self.make_relationship(self.carol, self.dev)

    def scope(self, **raw):
        scope, _ = sanitise_scope(raw, self.canonical())
        return scope

    def published(self, **raw):
        return apply_scope(self.canonical(), self.scope(**raw))

    def names(self, dataset):
        return sorted(o.name for o in dataset.objects.values())

    def status_filter(self, *values):
        return {"type_id": str(self.person_type.id), "key": "status", "op": "in", "value": list(values)}


class WholeModelTests(ScopeFixture):

    def test_an_empty_scope_publishes_everything(self):
        published = self.published()

        self.assertEqual(self.names(published), ["Alice", "Bob", "Carol", "Dev", "Ops"])
        self.assertEqual(len(published.relationships), 3)
        self.assertTrue(PublicationScope().is_whole_model)

    def test_the_result_never_carries_proposal_markers(self):
        published = self.published()

        self.assertFalse(any(o.is_proposed or o.is_created for o in published.objects.values()))
        self.assertFalse(any(r.is_proposed or r.is_created for r in published.relationships.values()))


class ExclusionTests(ScopeFixture):

    def test_excluding_an_object_type_removes_its_objects_and_their_relationships(self):
        published = self.published(object_types={"excluded": [str(self.team_type.id)]})

        self.assertEqual(self.names(published), ["Alice", "Bob", "Carol"])
        self.assertEqual(len(published.relationships), 0)
        self.assertNotIn(str(self.team_type.id), published.object_types)

    def test_excluding_a_relationship_type_keeps_the_endpoints(self):
        published = self.published(relationship_types={"excluded": [str(self.member_of.id)]})

        self.assertEqual(self.names(published), ["Alice", "Bob", "Carol", "Dev", "Ops"])
        self.assertEqual(len(published.relationships), 0)
        self.assertNotIn(str(self.member_of.id), published.relationship_types)

    def test_an_attribute_filter_constrains_only_objects_of_its_own_type(self):
        published = self.published(attribute_filters=[self.status_filter("Active")])

        # Bob (Left) is gone, and so is his relationship; teams are unaffected.
        self.assertEqual(self.names(published), ["Alice", "Carol", "Dev", "Ops"])
        self.assertEqual(len(published.relationships), 2)

    def test_rules_naming_an_excluded_type_are_dropped(self):
        published = self.published(object_types={"excluded": [str(self.team_type.id)]})

        # member_of survives (it is not excluded) but its Person->Team rule must not.
        self.assertEqual(published.relationship_types[str(self.member_of.id)].rules, ())

    def test_excluded_data_leaves_no_trace(self):
        self.make_object(self.team_type, "Secret Project Zeta")

        published = self.published(object_types={"excluded": [str(self.team_type.id)]})

        self.assertNotIn("Secret Project Zeta", repr(published.objects))
        self.assertNotIn("Ops", repr(published.objects))


class TraversalTests(ScopeFixture):

    def reach(self, depth, roots=None):
        roots = [str(self.alice.id)] if roots is None else roots
        return self.names(self.published(traversal={"roots": roots, "depth": depth}))

    def test_depth_zero_is_the_starting_objects_only(self):
        self.assertEqual(self.reach(0), ["Alice"])

    def test_depth_one_adds_direct_connections_in_either_direction(self):
        self.assertEqual(self.reach(1), ["Alice", "Ops"])
        # Following the relationship backwards (Ops <- Alice) works too.
        self.assertEqual(self.reach(1, roots=[str(self.ops.id)]), ["Alice", "Bob", "Ops"])

    def test_deeper_depth_keeps_walking(self):
        self.assertEqual(self.reach(2), ["Alice", "Bob", "Ops"])

    def test_unlimited_depth_stops_at_the_end_of_the_component(self):
        self.assertEqual(self.reach(None), ["Alice", "Bob", "Ops"])

    def test_only_relationships_among_kept_objects_remain(self):
        published = self.published(traversal={"roots": [str(self.alice.id)], "depth": 1})

        self.assertEqual([r.id for r in published.relationships.values()], [str(self.r_alice.id)])

    def test_several_starting_objects_are_unioned(self):
        self.assertEqual(self.reach(0, roots=[str(self.alice.id), str(self.carol.id)]), ["Alice", "Carol"])

    def test_exclusions_win_over_traversal(self):
        published = self.published(
            object_types={"excluded": [str(self.team_type.id)]},
            traversal={"roots": [str(self.alice.id)], "depth": 3},
        )

        # Ops is excluded, so nothing beyond it (Bob) is reachable either.
        self.assertEqual(self.names(published), ["Alice"])

    def test_a_starting_object_removed_by_a_filter_is_not_resurrected(self):
        published = self.published(
            attribute_filters=[self.status_filter("Left")],
            traversal={"roots": [str(self.alice.id)], "depth": 2},
        )

        self.assertEqual(self.names(published), [])

    def test_a_relationship_type_exclusion_blocks_the_path(self):
        published = self.published(
            relationship_types={"excluded": [str(self.member_of.id)]},
            traversal={"roots": [str(self.alice.id)], "depth": 3},
        )

        self.assertEqual(self.names(published), ["Alice"])


class DeterminismTests(ScopeFixture):

    def test_the_same_scope_gives_the_same_dataset(self):
        raw = {"traversal": {"roots": [str(self.ops.id)], "depth": 1}}

        first = self.published(**raw)
        second = self.published(**raw)

        self.assertEqual(list(first.objects), list(second.objects))
        self.assertEqual(list(first.relationships), list(second.relationships))


class AttributeCleaningTests(ScopeFixture):

    def test_only_populated_values_of_defined_attributes_are_published(self):
        Object.objects.filter(pk=self.alice.pk).update(
            attributes={"status": "Active", "removed_attribute": "sensitive", "blank": "", "nothing": None}
        )

        published = self.published()

        self.assertEqual(published.objects[str(self.alice.id)].attributes, {"status": "Active"})

    def test_whole_number_floats_are_written_as_integers(self):
        AttributeDefinition.objects.create(
            object_type=self.person_type,
            name="Age",
            key="age",
            data_type=AttributeDefinition.DataType.NUMBER,
        )
        Object.objects.filter(pk=self.alice.pk).update(attributes={"age": 30.0})

        published = self.published()

        value = published.objects[str(self.alice.id)].attributes["age"]
        self.assertEqual(value, 30)
        self.assertIsInstance(value, int)
