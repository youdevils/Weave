import json

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from workspace.models import Workspace, WorkspaceMember


class ObjectTypeAttributeChoiceConfigTests(TestCase):

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

        cls.object_type = ObjectType.objects.create(
            model=cls.model,
            name="Application",
            key="application",
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def edit_url(self):
        return reverse(
            "model:object_type_edit",
            args=[self.model.id, self.object_type.id],
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
                "attribute_name": "Status",
                "attribute_key": "status",
                "attribute_data_type": "choice",
                "attribute_choices": json.dumps(["Proposed", "Approved", "Live"]),
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", operation=ProposalChange.Operation.CREATE,
        )
        self.assertEqual(
            change.after["config"],
            {"choices": ["Proposed", "Approved", "Live"]},
        )

        # Survives refresh: GET re-renders from the same working proposal.
        get_response = self.client.get(self.edit_url())
        attributes = get_response.context["attributes"]
        status_attribute = next(a for a in attributes if a.proposed_values["key"] == "status")

        self.assertEqual(
            status_attribute.proposed_values["config"]["choices"],
            ["Proposed", "Approved", "Live"],
        )
        self.assertContains(get_response, "Proposed")
        self.assertContains(get_response, "Approved")

    def test_edit_existing_attribute_choice_values_records_config_update(self):
        attribute = AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.TEXT,
            is_active=True,
        )

        response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Status",
                "attribute_key": "status",
                "attribute_data_type": "choice",
                "attribute_choices": json.dumps(["Low", "High"]),
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", target_id=attribute.id, after__field="config",
        )
        self.assertEqual(change.after["value"], {"choices": ["Low", "High"]})

        # Canonical row is untouched.
        attribute.refresh_from_db()
        self.assertEqual(attribute.config, {})
        self.assertEqual(attribute.data_type, AttributeDefinition.DataType.TEXT)

    def test_choice_attribute_requires_at_least_one_value(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Status",
                "attribute_key": "status",
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
                "attribute_name": "Status",
                "attribute_key": "status",
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
                "attribute_name": "Status",
                "attribute_key": "status",
                "attribute_data_type": "choice",
                "attribute_choices": "not-json",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("choices", response.json()["errors"])

    def test_non_choice_attribute_editing_still_works_regression(self):
        attribute = AttributeDefinition.objects.create(
            object_type=self.object_type,
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
        """
        Guardrail: editing another attribute property must not clear an
        existing CHOICE attribute's allowed values.
        """

        attribute = AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Low", "High"]},
            is_active=True,
        )

        response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Status",
                "attribute_key": "status",
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
        status_attribute = next(
            a for a in get_response.context["attributes"] if a.key == "status"
        )
        self.assertEqual(
            status_attribute.proposed_values["config"]["choices"],
            ["Low", "High"],
        )

    def test_missing_choices_field_falls_back_to_existing_config_defensively(self):
        """
        If attribute_choices is ever absent from the POST entirely
        (shouldn't happen given the JS always sends it), the existing
        effective config must be preserved rather than cleared.
        """

        attribute = AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Low", "High"]},
            is_active=True,
        )

        response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Status",
                "attribute_key": "status",
                "attribute_data_type": "choice",
                # attribute_choices deliberately omitted.
            },
        )

        self.assertTrue(response.json()["success"])

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="AttributeDefinition", target_id=attribute.id, after__field="config",
            ).exists()
        )
