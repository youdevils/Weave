from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember


class OverviewOntologyGraphTests(TestCase):

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

    def setUp(self):
        self.client.force_login(self.user)

    def overview_url(self):
        return reverse("model:overview", args=[self.model.id])

    def test_context_includes_ontology_payload_with_active_object_type_node(self):
        object_type = ObjectType.objects.create(
            model=self.model,
            name="Application",
            key="application",
            is_active=True,
        )

        response = self.client.get(self.overview_url())

        payload = response.context["ontology_payload"]
        node_ids = {node["id"] for node in payload["nodes"]}
        self.assertIn(str(object_type.id), node_ids)

    def test_renders_payload_script_and_graph_container(self):
        response = self.client.get(self.overview_url())

        self.assertContains(response, 'id="model-ontology-payload"')
        self.assertContains(response, 'id="model-ontology-graph"')

    def test_empty_model_renders_successfully_with_empty_graph(self):
        response = self.client.get(self.overview_url())

        self.assertEqual(response.status_code, 200)
        payload = response.context["ontology_payload"]
        self.assertEqual(payload["nodes"], [])
        self.assertEqual(payload["edges"], [])

    def test_active_proposal_changes_are_reflected_in_rendered_payload(self):
        subject = ObjectType.objects.create(
            model=self.model, name="Subject", key="subject", is_active=True,
        )
        obj = ObjectType.objects.create(
            model=self.model, name="Object", key="object", is_active=True,
        )
        relationship_type = RelationshipType.objects.create(
            model=self.model, name="Relates to", key="relates_to", is_active=True,
        )
        rule = RelationshipTypeRule.objects.create(
            relationship_type=relationship_type,
            subject_type=subject,
            object_type=obj,
        )

        proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.WORKING,
        )

        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type="RelationshipType",
            target_id=relationship_type.id,
            after={"field": "name", "value": "Renamed Relationship"},
        )

        activate_proposal(self.client, self.model.id, proposal)

        response = self.client.get(self.overview_url())

        payload = response.context["ontology_payload"]
        edge = next(e for e in payload["edges"] if e["id"] == str(rule.id))
        self.assertEqual(edge["label"], "Renamed Relationship")
