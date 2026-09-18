from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.ontology_graph.compiler import compile_ontology_graph
from viewer.contracts import validate_payload
from workspace.models import Workspace, WorkspaceMember


class OntologyGraphCompilerTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="user@example.com",
            password="test-password",
        )

        WorkspaceMember.objects.create(
            workspace=cls.workspace,
            user=cls.user,
            role=WorkspaceMember.Role.OWNER,
        )

        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
            revision=1,
        )

    def make_object_type(self, **kwargs):
        defaults = {"model": self.model, "name": "Type", "key": "type", "is_active": True}
        defaults.update(kwargs)
        return ObjectType.objects.create(**defaults)

    def make_relationship_type(self, **kwargs):
        defaults = {"model": self.model, "name": "Relates to", "key": "relates_to", "is_active": True}
        defaults.update(kwargs)
        return RelationshipType.objects.create(**defaults)

    def make_rule(self, relationship_type, subject_type, object_type, **kwargs):
        defaults = {
            "relationship_type": relationship_type,
            "subject_type": subject_type,
            "object_type": object_type,
        }
        defaults.update(kwargs)
        return RelationshipTypeRule.objects.create(**defaults)

    def make_working_proposal(self):
        return Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.WORKING,
        )

    # -----------------------------------------------------------------
    # Node filtering
    # -----------------------------------------------------------------

    def test_only_active_object_types_become_nodes(self):
        active = self.make_object_type(name="Active", key="active", is_active=True)
        self.make_object_type(name="Inactive", key="inactive", is_active=False)

        payload = compile_ontology_graph(self.model)

        node_ids = {node.id for node in payload.nodes}
        self.assertEqual(node_ids, {str(active.id)})

    def test_node_uses_object_type_name_as_label(self):
        object_type = self.make_object_type(name="Application", key="application")

        payload = compile_ontology_graph(self.model)

        node = next(n for n in payload.nodes if n.id == str(object_type.id))
        self.assertEqual(node.label, "Application")

    # -----------------------------------------------------------------
    # Edge filtering
    # -----------------------------------------------------------------

    def test_only_rules_of_active_relationship_types_become_edges(self):
        subject = self.make_object_type(name="Subject", key="subject")
        obj = self.make_object_type(name="Object", key="object")

        active_rt = self.make_relationship_type(name="Active Rel", key="active_rel", is_active=True)
        self.make_rule(active_rt, subject, obj)

        inactive_rt = self.make_relationship_type(name="Inactive Rel", key="inactive_rel", is_active=False)
        self.make_rule(inactive_rt, subject, obj)

        payload = compile_ontology_graph(self.model)

        labels = {edge.label for edge in payload.edges}
        self.assertEqual(labels, {"Active Rel"})

    def test_rule_excluded_when_endpoint_object_type_is_inactive(self):
        subject = self.make_object_type(name="Subject", key="subject", is_active=True)
        obj = self.make_object_type(name="Object", key="object", is_active=False)

        rt = self.make_relationship_type()
        self.make_rule(rt, subject, obj)

        payload = compile_ontology_graph(self.model)

        self.assertEqual(payload.edges, [])
        self.assertEqual(validate_payload(payload), [])

    def test_edge_direction_reflects_subject_to_object(self):
        subject = self.make_object_type(name="Subject", key="subject")
        obj = self.make_object_type(name="Object", key="object")

        rt = self.make_relationship_type()
        self.make_rule(rt, subject, obj)

        payload = compile_ontology_graph(self.model)

        self.assertEqual(len(payload.edges), 1)
        edge = payload.edges[0]
        self.assertEqual(edge.source, str(subject.id))
        self.assertEqual(edge.target, str(obj.id))

    def test_edge_label_is_relationship_type_name(self):
        subject = self.make_object_type(name="Subject", key="subject")
        obj = self.make_object_type(name="Object", key="object")

        rt = self.make_relationship_type(name="Owns", key="owns")
        self.make_rule(rt, subject, obj)

        payload = compile_ontology_graph(self.model)

        self.assertEqual(payload.edges[0].label, "Owns")

    # -----------------------------------------------------------------
    # No instance data
    # -----------------------------------------------------------------

    def test_no_object_or_relationship_instance_data_is_included(self):
        subject_type = self.make_object_type(name="Subject", key="subject")
        object_type = self.make_object_type(name="Object", key="object")
        rt = self.make_relationship_type()
        self.make_rule(rt, subject_type, object_type)

        subject_obj = Object.objects.create(
            model=self.model,
            object_type=subject_type,
            name="Top Secret Instance Name",
            attributes={"secret": "instance-attribute-value"},
        )
        object_obj = Object.objects.create(
            model=self.model,
            object_type=object_type,
            name="Another Secret Instance",
            attributes={"secret": "other-instance-attribute-value"},
        )
        Relationship.objects.create(
            model=self.model,
            relationship_type=rt,
            subject=subject_obj,
            object=object_obj,
            attributes={"secret": "relationship-instance-attribute"},
        )

        payload = compile_ontology_graph(self.model)
        serialised = payload.to_dict()

        node_ids = {node.id for node in payload.nodes}
        self.assertEqual(node_ids, {str(subject_type.id), str(object_type.id)})

        blob = str(serialised)
        self.assertNotIn("Top Secret Instance Name", blob)
        self.assertNotIn("Another Secret Instance", blob)
        self.assertNotIn("instance-attribute-value", blob)
        self.assertNotIn("relationship-instance-attribute", blob)

    # -----------------------------------------------------------------
    # No proposal
    # -----------------------------------------------------------------

    def test_no_proposal_reflects_canonical_state_only(self):
        object_type = self.make_object_type(name="Canonical", key="canonical")

        payload = compile_ontology_graph(self.model, None)

        node = payload.nodes[0]
        self.assertEqual(node.id, str(object_type.id))
        self.assertFalse(node.data["is_proposed"])
        self.assertEqual(node.style.border, "#4C6EF5")
        self.assertEqual(validate_payload(payload), [])

    # -----------------------------------------------------------------
    # Proposal overlay
    # -----------------------------------------------------------------

    def test_proposed_create_object_type_appears_as_proposed_node(self):
        proposal = self.make_working_proposal()

        import uuid

        new_id = uuid.uuid4()
        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=new_id,
            parent_type="Model",
            after={"name": "Proposed Type", "key": "proposed_type", "is_active": True},
        )

        payload = compile_ontology_graph(self.model, proposal)

        node = next(n for n in payload.nodes if n.id == str(new_id))
        self.assertEqual(node.label, "Proposed Type")
        self.assertTrue(node.data["is_proposed"])
        self.assertEqual(node.style.border, "#F08C00")
        self.assertEqual(validate_payload(payload), [])

    def test_proposed_deactivation_removes_node(self):
        object_type = self.make_object_type(name="Will Be Deactivated", key="deactivated", is_active=True)
        proposal = self.make_working_proposal()

        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type="ObjectType",
            target_id=object_type.id,
            after={"field": "is_active", "value": False},
        )

        payload = compile_ontology_graph(self.model, proposal)

        node_ids = {node.id for node in payload.nodes}
        self.assertNotIn(str(object_type.id), node_ids)
        self.assertEqual(validate_payload(payload), [])

    def test_proposed_rule_appears_as_proposed_dashed_edge(self):
        subject = self.make_object_type(name="Subject", key="subject")
        obj = self.make_object_type(name="Object", key="object")
        rt = self.make_relationship_type(name="Relates", key="relates")

        proposal = self.make_working_proposal()

        import uuid

        rule_id = uuid.uuid4()
        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipTypeRule",
            target_id=rule_id,
            parent_type="RelationshipType",
            parent_id=rt.id,
            after={
                "subject_type_id": str(subject.id),
                "object_type_id": str(obj.id),
                "subject_minimum": 0,
                "object_minimum": 0,
            },
        )

        payload = compile_ontology_graph(self.model, proposal)

        edge = next(e for e in payload.edges if e.id == str(rule_id))
        self.assertTrue(edge.data["is_proposed"])
        self.assertEqual(edge.style.colour, "#F08C00")
        self.assertTrue(edge.style.dashes)
        self.assertEqual(validate_payload(payload), [])

    def test_proposed_relationship_type_rename_is_reflected_in_edge_label(self):
        subject = self.make_object_type(name="Subject", key="subject")
        obj = self.make_object_type(name="Object", key="object")
        rt = self.make_relationship_type(name="Old Name", key="old_name")
        rule = self.make_rule(rt, subject, obj)

        proposal = self.make_working_proposal()

        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type="RelationshipType",
            target_id=rt.id,
            after={"field": "name", "value": "New Name"},
        )

        payload = compile_ontology_graph(self.model, proposal)

        edge = next(e for e in payload.edges if e.id == str(rule.id))
        self.assertEqual(edge.label, "New Name")
        self.assertEqual(validate_payload(payload), [])

    def test_empty_model_produces_valid_empty_payload(self):
        payload = compile_ontology_graph(self.model)

        self.assertEqual(payload.nodes, [])
        self.assertEqual(payload.edges, [])
        self.assertEqual(validate_payload(payload), [])
