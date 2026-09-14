import json

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from workspace.models import Workspace, WorkspaceMember


class RelationshipTypeAttributeChoiceConfigTests(TestCase):

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

        cls.relationship_type = RelationshipType.objects.create(
            model=cls.model,
            name="Uses",
            key="uses",
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def edit_url(self):
        return reverse(
            "model:relationship_type_edit",
            args=[self.model.id, self.relationship_type.id],
        )

    def working_proposal(self):
        return Proposal.objects.get(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )

    def test_create_choice_attribute_with_allowed_values_persists_on_refresh(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Criticality",
                "attribute_key": "criticality",
                "attribute_data_type": "choice",
                "attribute_choices": json.dumps(["Low", "Medium", "High"]),
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", operation=ProposalChange.Operation.CREATE,
        )
        self.assertEqual(
            change.after["config"],
            {"choices": ["Low", "Medium", "High"]},
        )

        get_response = self.client.get(self.edit_url())
        attributes = get_response.context["attributes"]
        criticality_attribute = next(
            a for a in attributes if a.proposed_values["key"] == "criticality"
        )
        self.assertEqual(
            criticality_attribute.proposed_values["config"]["choices"],
            ["Low", "Medium", "High"],
        )
        self.assertContains(get_response, "Medium")

    def test_edit_existing_attribute_choice_values_records_config_update(self):
        attribute = AttributeDefinition.objects.create(
            relationship_type=self.relationship_type,
            name="Criticality",
            key="criticality",
            data_type=AttributeDefinition.DataType.TEXT,
            is_active=True,
        )

        response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Criticality",
                "attribute_key": "criticality",
                "attribute_data_type": "choice",
                "attribute_choices": json.dumps(["Low", "High"]),
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", target_id=attribute.id, after__field="config",
        )
        self.assertEqual(change.after["value"], {"choices": ["Low", "High"]})

        attribute.refresh_from_db()
        self.assertEqual(attribute.config, {})
        self.assertEqual(attribute.data_type, AttributeDefinition.DataType.TEXT)

    def test_choice_attribute_requires_at_least_one_value(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Criticality",
                "attribute_key": "criticality",
                "attribute_data_type": "choice",
                "attribute_choices": json.dumps([]),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("choices", response.json()["errors"])
        self.assertFalse(ProposalChange.objects.filter(target_type="AttributeDefinition").exists())

    def test_choice_values_must_be_unique(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Criticality",
                "attribute_key": "criticality",
                "attribute_data_type": "choice",
                "attribute_choices": json.dumps(["Low", "Low"]),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("choices", response.json()["errors"])

    def test_malformed_choices_payload_rejected(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Criticality",
                "attribute_key": "criticality",
                "attribute_data_type": "choice",
                "attribute_choices": "not-json",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("choices", response.json()["errors"])

    def test_non_choice_attribute_editing_still_works_regression(self):
        attribute = AttributeDefinition.objects.create(
            relationship_type=self.relationship_type,
            name="Owner",
            key="owner",
            data_type=AttributeDefinition.DataType.TEXT,
            is_active=True,
        )

        response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Owner",
                "attribute_key": "owner",
                "attribute_data_type": "text",
                "attribute_description": "Updated description",
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", target_id=attribute.id, after__field="description",
        )
        self.assertEqual(change.after["value"], "Updated description")

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="AttributeDefinition", target_id=attribute.id, after__field="config",
            ).exists()
        )

    def test_editing_unrelated_field_preserves_existing_choice_values(self):
        attribute = AttributeDefinition.objects.create(
            relationship_type=self.relationship_type,
            name="Criticality",
            key="criticality",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Low", "High"]},
            is_active=True,
        )

        response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Criticality",
                "attribute_key": "criticality",
                "attribute_data_type": "choice",
                "attribute_description": "Now with a description",
                "attribute_choices": json.dumps(["Low", "High"]),
            },
        )

        self.assertTrue(response.json()["success"])

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="AttributeDefinition", target_id=attribute.id, after__field="config",
            ).exists()
        )

        get_response = self.client.get(self.edit_url())
        criticality_attribute = next(
            a for a in get_response.context["attributes"] if a.key == "criticality"
        )
        self.assertEqual(
            criticality_attribute.proposed_values["config"]["choices"],
            ["Low", "High"],
        )
