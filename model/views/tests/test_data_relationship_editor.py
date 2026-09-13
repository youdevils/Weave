from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from workspace.models import Workspace, WorkspaceMember


class DataRelationshipEditorTestCase(TestCase):

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

        cls.process_type = ObjectType.objects.create(
            model=cls.model, name="Process", key="process", is_active=True,
        )
        cls.app_type = ObjectType.objects.create(
            model=cls.model, name="Application", key="application", is_active=True,
        )
        cls.team_type = ObjectType.objects.create(
            model=cls.model, name="Team", key="team", is_active=True,
        )

        cls.uses_type = RelationshipType.objects.create(
            model=cls.model, name="Uses", key="uses", is_active=True,
        )

        RelationshipTypeRule.objects.create(
            relationship_type=cls.uses_type,
            subject_type=cls.process_type,
            object_type=cls.app_type,
        )

        cls.criticality_attribute = AttributeDefinition.objects.create(
            relationship_type=cls.uses_type,
            name="Criticality",
            key="criticality",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Low", "High"]},
            is_active=True,
        )

        cls.finance = Object.objects.create(
            model=cls.model, object_type=cls.process_type, name="Finance Reporting",
        )
        cls.power_bi = Object.objects.create(
            model=cls.model, object_type=cls.app_type, name="Power BI",
        )
        cls.team = Object.objects.create(
            model=cls.model, object_type=cls.team_type, name="Finance Team",
        )

    def setUp(self):
        self.client.force_login(self.user)

    def create_url(self):
        return reverse(
            "model:data_relationship_create",
            args=[self.model.id, self.uses_type.id],
        )

    def edit_url(self, relationship_id):
        return reverse(
            "model:data_relationship_edit",
            args=[self.model.id, self.uses_type.id, relationship_id],
        )

    def working_proposal(self):
        return Proposal.objects.get(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )


class CreateRelationshipTests(DataRelationshipEditorTestCase):

    def test_create_with_allowed_endpoints_records_proposal(self):
        response = self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.power_bi.id),
                "attr_criticality": "High",
            },
        )

        self.assertEqual(response.status_code, 302)

        proposal = self.working_proposal()
        change = proposal.changes.get(target_type="Relationship")

        self.assertEqual(change.operation, ProposalChange.Operation.CREATE)
        self.assertEqual(change.after["subject_id"], str(self.finance.id))
        self.assertEqual(change.after["object_id"], str(self.power_bi.id))
        self.assertEqual(change.after["attributes"]["criticality"], "High")

        self.assertEqual(Relationship.objects.filter(model=self.model).count(), 0)

        review_response = self.client.get(reverse("model:proposal", args=[self.model.id]))
        self.assertContains(review_response, "Finance Reporting")

    def test_create_rejects_endpoint_pair_not_permitted_by_rule(self):
        # Team is not an allowed object type for the Uses relationship's
        # single rule (Process -> Application).
        response = self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.team.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProposalChange.objects.filter(target_type="Relationship").exists())

    def test_create_requires_both_endpoints(self):
        response = self.client.post(self.create_url(), {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a subject.")
        self.assertContains(response, "Choose an object.")
        self.assertFalse(ProposalChange.objects.filter(target_type="Relationship").exists())


class UpdateRelationshipTests(DataRelationshipEditorTestCase):

    def setUp(self):
        super().setUp()

        self.relationship = Relationship.objects.create(
            model=self.model,
            relationship_type=self.uses_type,
            subject=self.finance,
            object=self.power_bi,
            attributes={"criticality": "Low"},
        )

    def test_attribute_value_update_records_dot_namespaced_change(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "High"},
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="Relationship", after__field="attributes.criticality",
        )
        self.assertEqual(change.after["value"], "High")

        self.relationship.refresh_from_db()
        self.assertEqual(self.relationship.attributes["criticality"], "Low")

        get_response = self.client.get(self.edit_url(self.relationship.id))
        self.assertEqual(
            get_response.context["proposed_values"]["attributes"]["criticality"],
            "High",
        )

    def test_invalid_choice_value_rejected(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "Medium"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            ProposalChange.objects.filter(after__field="attributes.criticality").exists()
        )

    def test_lifecycle_toggle_records_change_and_canonical_unchanged(self):
        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"action": "set_relationship_status", "is_active": "false"},
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="Relationship", after__field="is_active",
        )
        self.assertIs(change.after["value"], False)

        self.relationship.refresh_from_db()
        self.assertTrue(self.relationship.is_active)

    def test_discard_removes_change(self):
        self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "value": "High"},
        )

        response = self.client.post(
            self.edit_url(self.relationship.id),
            {"field": "attributes.criticality", "action": "discard"},
        )

        self.assertTrue(response.json()["success"])
        self.assertFalse(
            ProposalChange.objects.filter(after__field="attributes.criticality").exists()
        )


class ProposalOnlyRelationshipTests(DataRelationshipEditorTestCase):

    def _create_proposal_only_relationship(self):
        self.client.post(
            self.create_url(),
            {
                "subject_id": str(self.finance.id),
                "object_id": str(self.power_bi.id),
            },
        )

        change = ProposalChange.objects.get(
            target_type="Relationship", operation=ProposalChange.Operation.CREATE,
        )

        return change.target_id

    def test_editing_proposal_only_relationship_mutates_create_change(self):
        relationship_id = self._create_proposal_only_relationship()

        response = self.client.post(
            self.edit_url(relationship_id),
            {"field": "attributes.criticality", "value": "High"},
        )

        self.assertTrue(response.json()["success"])

        changes = ProposalChange.objects.filter(
            target_type="Relationship", target_id=relationship_id,
        )
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.first().after["attributes"]["criticality"], "High")

    def test_discard_removes_proposal_only_relationship_entirely(self):
        relationship_id = self._create_proposal_only_relationship()

        proposal = self.working_proposal()

        response = self.client.post(
            reverse("model:data_relationships", args=[self.model.id, self.uses_type.id]),
            {"action": "discard_relationship_proposal", "relationship_id": str(relationship_id)},
        )

        self.assertTrue(response.json()["success"])
        self.assertFalse(proposal.changes.filter(target_type="Relationship").exists())
        self.assertEqual(Relationship.objects.filter(model=self.model).count(), 0)
