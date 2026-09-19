import uuid

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.model_graph.loader import load_effective_dataset
from workspace.models import Workspace

from .base import ModelGraphTestCase

Op = ProposalChange.Operation


class CanonicalLoadingTests(ModelGraphTestCase):

    def test_active_objects_and_relationships_are_loaded(self):
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        relationship = self.make_relationship(alice, ops)

        dataset = load_effective_dataset(self.model)

        self.assertEqual(set(dataset.objects), {str(alice.id), str(ops.id)})
        loaded = dataset.relationship(relationship.id)
        self.assertEqual((loaded.source_id, loaded.target_id), (str(alice.id), str(ops.id)))  # direction kept
        self.assertFalse(loaded.is_proposed)

    def test_inactive_objects_and_their_relationships_are_excluded(self):
        alice = self.make_object(self.person_type, "Alice")
        bob = self.make_object(self.person_type, "Bob", is_active=False)
        ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(alice, ops)
        self.make_relationship(bob, ops)

        dataset = load_effective_dataset(self.model)

        self.assertNotIn(str(bob.id), dataset.objects)
        self.assertEqual(len(dataset.relationships), 1)

    def test_inactive_relationships_are_excluded(self):
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(alice, ops, is_active=False)

        self.assertEqual(load_effective_dataset(self.model).relationships, {})

    def test_model_containing_only_inactive_objects_is_empty(self):
        self.make_object(self.person_type, "Ghost", is_active=False)

        dataset = load_effective_dataset(self.model)

        self.assertEqual((dataset.objects, dataset.relationships), ({}, {}))
        # The types still exist, so the Explorer can describe an empty model.
        self.assertEqual(len(dataset.object_types), 2)

    def test_empty_model(self):
        dataset = load_effective_dataset(self.model)

        self.assertEqual((dataset.objects, dataset.relationships), ({}, {}))

    def test_objects_of_a_retired_type_are_excluded(self):
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(alice, ops)
        self.team_type.is_active = False
        self.team_type.save()

        dataset = load_effective_dataset(self.model)

        self.assertEqual(set(dataset.objects), {str(alice.id)})
        self.assertEqual(dataset.relationships, {})  # its endpoint is gone

    def test_relationships_of_a_retired_relationship_type_are_excluded(self):
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(alice, ops)
        self.member_of.is_active = False
        self.member_of.save()

        dataset = load_effective_dataset(self.model)

        self.assertEqual(len(dataset.objects), 2)
        self.assertEqual(dataset.relationships, {})

    def test_other_models_data_is_never_loaded(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        other_type = ObjectType.objects.create(model=other, name="Thing", key="thing", is_active=True)
        Object.objects.create(model=other, object_type=other_type, name="Elsewhere")

        self.assertEqual(load_effective_dataset(self.model).objects, {})

    def test_attribute_specs_and_choices_are_loaded(self):
        dataset = load_effective_dataset(self.model)

        (status,) = dataset.object_type(self.person_type.id).attributes
        self.assertEqual((status.key, status.data_type, status.choices), ("status", "choice", ("Active", "Left")))

    def test_url_datatype_is_carried_into_the_spec_and_details_next_to_the_value(self):
        from model.services.model_graph.details import object_details

        AttributeDefinition.objects.create(
            object_type=self.person_type, name="Website", key="website", data_type=AttributeDefinition.DataType.URL
        )
        AttributeDefinition.objects.create(
            object_type=self.person_type, name="Notes", key="notes", data_type=AttributeDefinition.DataType.TEXT
        )
        alice = self.make_object(
            self.person_type, "Alice", attributes={"website": "https://example.com/a", "notes": "https://example.com/b"}
        )

        dataset = load_effective_dataset(self.model)

        specs = {spec.key: spec.data_type for spec in dataset.object_type(self.person_type.id).attributes}
        self.assertEqual(specs["website"], "url")
        self.assertEqual(specs["notes"], "text")

        by_key = {a["key"]: a for a in object_details(dataset, alice.id)["attributes"]}
        self.assertEqual((by_key["website"]["dataType"], by_key["website"]["value"]), ("url", "https://example.com/a"))
        self.assertEqual((by_key["notes"]["dataType"], by_key["notes"]["value"]), ("text", "https://example.com/b"))

    def test_url_datatype_is_carried_for_relationship_attributes(self):
        from model.services.model_graph.details import relationship_details

        AttributeDefinition.objects.create(
            relationship_type=self.member_of, name="Charter", key="charter", data_type=AttributeDefinition.DataType.URL
        )
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        membership = self.make_relationship(alice, ops, attributes={"charter": "https://example.com/charter"})

        details = relationship_details(load_effective_dataset(self.model), membership.id)

        (charter,) = details["attributes"]
        self.assertEqual((charter["dataType"], charter["value"]), ("url", "https://example.com/charter"))

    def test_inactive_attribute_definitions_are_excluded(self):
        self.status_attribute.is_active = False
        self.status_attribute.save()

        self.assertEqual(load_effective_dataset(self.model).object_type(self.person_type.id).attributes, ())

    def test_cardinality_rules_are_loaded(self):
        dataset = load_effective_dataset(self.model)

        (rule,) = dataset.relationship_type(self.member_of.id).rules
        self.assertEqual((rule.subject_type_id, rule.object_type_id), (str(self.person_type.id), str(self.team_type.id)))

    def test_objects_with_missing_or_empty_attributes_load(self):
        bare = self.make_object(self.person_type, "Bare")
        blank = self.make_object(self.person_type, "Blank", attributes={"status": ""})

        dataset = load_effective_dataset(self.model)

        self.assertEqual(dataset.object(bare.id).attributes, {})
        self.assertEqual(dataset.object(blank.id).attributes, {"status": ""})

    def test_relationship_validity_dates_are_carried(self):
        from django.utils import timezone

        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        moment = timezone.now()
        relationship = self.make_relationship(alice, ops, valid_from=moment)

        loaded = load_effective_dataset(self.model).relationship(relationship.id)

        self.assertEqual(loaded.valid_from, moment.isoformat())
        self.assertIsNone(loaded.valid_to)


class ProposalOverlayTests(ModelGraphTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.membership = self.make_relationship(self.alice, self.ops)

    def test_without_a_proposal_only_canonical_state_is_shown(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Draft")

        dataset = load_effective_dataset(self.model, None)

        self.assertEqual(sorted(o.name for o in dataset.objects.values()), ["Alice", "Ops"])
        self.assertFalse(any(o.is_proposed for o in dataset.objects.values()))

    def test_proposed_object_appears_as_created_and_proposed(self):
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.person_type.id, "Draft", {"status": "Left"})

        dataset = load_effective_dataset(self.model, proposal)

        draft = dataset.object(draft_id)
        self.assertEqual((draft.name, draft.type_id), ("Draft", str(self.person_type.id)))
        self.assertEqual(draft.attributes, {"status": "Left"})
        self.assertTrue(draft.is_proposed and draft.is_created)
        self.assertFalse(dataset.object(self.alice.id).is_proposed)

    def test_proposed_rename_and_attribute_update_overlay_canonical_objects(self):
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "name", "Alicia")
        self.update(proposal, "Object", self.alice.id, "attributes.status", "Left")

        alice = load_effective_dataset(self.model, proposal).object(self.alice.id)

        self.assertEqual((alice.name, alice.attributes["status"]), ("Alicia", "Left"))
        self.assertTrue(alice.is_proposed)
        self.assertFalse(alice.is_created)

    def test_later_updates_to_the_same_field_win(self):
        proposal = self.working_proposal()
        first = self.update(proposal, "Object", self.alice.id, "name", "First")
        second = self.update(proposal, "Object", self.alice.id, "name", "Second")
        # Pin the order: the Windows clock can tick coarsely enough to tie created_at.
        from datetime import timedelta

        ProposalChange.objects.filter(pk=first.pk).update(created_at=second.created_at - timedelta(seconds=5))

        self.assertEqual(load_effective_dataset(self.model, proposal).object(self.alice.id).name, "Second")

    def test_proposed_deactivation_removes_the_object_and_its_relationships(self):
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "is_active", False)

        dataset = load_effective_dataset(self.model, proposal)

        self.assertIsNone(dataset.object(self.alice.id))
        self.assertEqual(dataset.relationships, {})
        self.assertIsNotNone(dataset.object(self.ops.id))

    def test_proposed_reactivation_brings_an_inactive_object_back(self):
        ghost = self.make_object(self.person_type, "Ghost", is_active=False)
        proposal = self.working_proposal()
        self.update(proposal, "Object", ghost.id, "is_active", True)

        self.assertIsNotNone(load_effective_dataset(self.model, proposal).object(ghost.id))
        self.assertIsNone(load_effective_dataset(self.model, None).object(ghost.id))

    def test_proposed_object_delete_removes_it_and_its_relationships(self):
        proposal = self.working_proposal()
        self.add_change(proposal, operation=Op.DELETE, target_type="Object", target_id=self.ops.id)

        dataset = load_effective_dataset(self.model, proposal)

        self.assertIsNone(dataset.object(self.ops.id))
        self.assertEqual(dataset.relationships, {})

    def test_proposed_relationship_delete_and_deactivation(self):
        other = self.make_relationship(self.make_object(self.person_type, "Bob"), self.ops)
        proposal = self.working_proposal()
        self.add_change(proposal, operation=Op.DELETE, target_type="Relationship", target_id=self.membership.id)
        self.update(proposal, "Relationship", other.id, "is_active", False)

        self.assertEqual(load_effective_dataset(self.model, proposal).relationships, {})

    def test_proposed_relationship_between_canonical_objects(self):
        bob = self.make_object(self.person_type, "Bob")
        proposal = self.working_proposal()
        relationship_id = self.propose_relationship(proposal, bob.id, self.ops.id)

        relationship = load_effective_dataset(self.model, proposal).relationship(relationship_id)

        self.assertEqual((relationship.source_id, relationship.target_id), (str(bob.id), str(self.ops.id)))
        self.assertTrue(relationship.is_proposed and relationship.is_created)

    def test_proposed_relationship_to_a_proposed_object(self):
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.team_type.id, "Draft Team")
        relationship_id = self.propose_relationship(proposal, self.alice.id, draft_id)

        dataset = load_effective_dataset(self.model, proposal)

        self.assertEqual(dataset.relationship(relationship_id).target_id, str(draft_id))

    def test_proposed_url_attribute_definition_keeps_its_datatype(self):
        proposal = self.working_proposal()
        self.add_change(
            proposal,
            operation=Op.CREATE,
            target_type="AttributeDefinition",
            target_id=uuid.uuid4(),
            parent_type="ObjectType",
            parent_id=self.person_type.id,
            after={"name": "Website", "key": "website", "data_type": "url", "is_active": True},
        )

        dataset = load_effective_dataset(self.model, proposal)

        specs = {spec.key: spec.data_type for spec in dataset.object_type(self.person_type.id).attributes}
        self.assertEqual(specs["website"], "url")

    def test_proposed_object_of_a_proposed_type(self):
        proposal = self.working_proposal()
        type_id = uuid.uuid4()
        self.add_change(
            proposal,
            operation=Op.CREATE,
            target_type="ObjectType",
            target_id=type_id,
            parent_type="Model",
            parent_id=self.model.id,
            after={"name": "Widget", "key": "widget", "description": "", "sort_order": 0, "is_active": True},
        )
        widget_id = self.propose_object(proposal, type_id, "Gizmo")

        dataset = load_effective_dataset(self.model, proposal)

        self.assertEqual(dataset.object(widget_id).type_id, str(type_id))
        self.assertTrue(dataset.object_type(type_id).is_proposed)

    def test_proposed_deactivation_of_a_type_hides_its_objects(self):
        proposal = self.working_proposal()
        self.update(proposal, "ObjectType", self.team_type.id, "is_active", False)

        dataset = load_effective_dataset(self.model, proposal)

        self.assertIsNone(dataset.object(self.ops.id))
        self.assertEqual(dataset.relationships, {})

    def test_relationship_to_a_missing_or_deleted_endpoint_is_dropped(self):
        proposal = self.working_proposal()
        relationship_id = self.propose_relationship(proposal, self.alice.id, uuid.uuid4())

        self.assertIsNone(load_effective_dataset(self.model, proposal).relationship(relationship_id))

    def test_relationship_to_a_proposed_object_that_is_deactivated_is_dropped(self):
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.team_type.id, "Draft", is_active=False)
        relationship_id = self.propose_relationship(proposal, self.alice.id, draft_id)

        self.assertIsNone(load_effective_dataset(self.model, proposal).relationship(relationship_id))

    def test_proposed_rename_is_reflected_for_relationship_endpoints(self):
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.ops.id, "name", "Operations")

        dataset = load_effective_dataset(self.model, proposal)
        relationship = dataset.relationship(self.membership.id)

        self.assertEqual(dataset.objects[relationship.target_id].name, "Operations")

    def test_proposed_relationship_attribute_update(self):
        proposal = self.working_proposal()
        self.update(proposal, "Relationship", self.membership.id, "attributes.since", "2020-01-01")

        relationship = load_effective_dataset(self.model, proposal).relationship(self.membership.id)

        self.assertEqual(relationship.attributes["since"], "2020-01-01")
        self.assertTrue(relationship.is_proposed)

    def test_another_proposals_changes_are_not_applied(self):
        mine = self.working_proposal()
        other_user = CustomUser.objects.create_user(email="other@example.com", password="test-password")
        theirs = Proposal.objects.create(model=self.model, created_by=other_user, status=Proposal.Status.WORKING)
        self.update(theirs, "Object", self.alice.id, "name", "Theirs")

        self.assertEqual(load_effective_dataset(self.model, mine).object(self.alice.id).name, "Alice")

    def test_a_proposal_that_only_touches_the_ontology_changes_no_data(self):
        proposal = self.working_proposal()
        self.update(proposal, "ObjectType", self.person_type.id, "name", "Human")

        dataset = load_effective_dataset(self.model, proposal)

        self.assertEqual(dataset.object_type(self.person_type.id).name, "Human")
        self.assertFalse(dataset.object(self.alice.id).is_proposed)


class QueryCountTests(ModelGraphTestCase):

    def count_queries(self, proposal):
        with CaptureQueriesContext(connection) as context:
            load_effective_dataset(self.model, proposal)
        return len(context)

    def test_query_count_does_not_grow_with_the_amount_of_data(self):
        proposal = self.working_proposal()
        ops = self.make_object(self.team_type, "Ops")
        people = [self.make_object(self.person_type, f"P{n}") for n in range(3)]
        for person in people:
            self.make_relationship(person, ops)
        self.update(proposal, "Object", people[0].id, "name", "Renamed")
        self.propose_object(proposal, self.person_type.id, "Draft")
        small = self.count_queries(proposal)

        for n in range(3, 40):
            person = self.make_object(self.person_type, f"P{n}")
            self.make_relationship(person, ops)
            self.update(proposal, "Object", person.id, "attributes.status", "Left")
            self.propose_object(proposal, self.person_type.id, f"Draft {n}")

        self.assertEqual(self.count_queries(proposal), small)

    def test_no_proposal_needs_no_change_queries(self):
        self.make_object(self.person_type, "Alice")

        self.assertLessEqual(self.count_queries(None), self.count_queries(self.working_proposal()))
