import json
import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.views.tests.proposal_test_utils import activate_proposal
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

    def test_create_url_attribute_is_recorded_with_url_datatype(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Website",
                "attribute_key": "website",
                "attribute_data_type": "url",
                "attribute_default_value": "not validated as a url",
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", operation=ProposalChange.Operation.CREATE,
        )
        self.assertEqual(change.after["data_type"], "url")
        self.assertEqual(change.after["config"], {})
        self.assertEqual(change.after["default_value"], "not validated as a url")

        page = self.client.get(self.edit_url())
        self.assertContains(page, 'value="url"')

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


class ObjectTypeEditorProposalCapTests(TestCase):
    """
    The implicit auto-create-on-edit path must respect the live
    proposal cap just like the explicit "+ New proposal" action --
    it's the highest-regression-risk piece of the multi-proposal
    refactor since it now runs on every editor write path.
    """

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

    def test_edit_with_no_active_proposal_auto_creates_one(self):
        response = self.client.post(
            self.edit_url(),
            {"field": "description", "value": "A new description"},
        )

        self.assertTrue(response.json()["success"])
        self.assertEqual(
            Proposal.objects.filter(model=self.model, created_by=self.user).count(),
            1,
        )

    def test_edit_is_rejected_once_the_live_proposal_cap_is_reached(self):
        for _ in range(5):
            Proposal.objects.create(
                model=self.model,
                created_by=self.user,
                status=Proposal.Status.WORKING,
            )

        # Fresh session -- no active proposal pointer -- yet 5 live
        # proposals already exist for this (model, user).
        response = self.client.post(
            self.edit_url(),
            {"field": "description", "value": "Should not be recorded"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["success"])
        self.assertEqual(
            Proposal.objects.filter(model=self.model, created_by=self.user).count(),
            5,
        )
        self.assertFalse(
            ProposalChange.objects.filter(after__field="description").exists()
        )


class AIProposalObjectTypeEditingTests(TestCase):
    """
    End-to-end regression for the active-proposal generalisation: an
    AI-created proposal-only ObjectType can be opened and edited through
    the normal editor, and the edit lands on the SAME AI proposal rather
    than spawning (or falling back to) a separate USER proposal.
    """

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="ai-editor@example.com",
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

        self.ai_proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.AI,
            status=Proposal.Status.WORKING,
        )

        self.proposed_object_type_id = uuid.uuid4()

        self.create_change = ProposalChange.objects.create(
            proposal=self.ai_proposal,
            source=ProposalChange.Source.AI,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=self.proposed_object_type_id,
            parent_type="Model",
            parent_id=self.model.id,
            after={
                "name": "Widget",
                "key": "widget",
                "sort_order": 0,
                "is_active": True,
                "description": "",
            },
        )

        activate_proposal(self.client, self.model.id, self.ai_proposal)

    def edit_url(self):
        return reverse(
            "model:object_type_edit",
            args=[self.model.id, self.proposed_object_type_id],
        )

    def test_editing_an_ai_proposed_object_type_updates_the_same_ai_proposal(self):
        response = self.client.post(
            self.edit_url(),
            {"field": "description", "value": "Edited by a human reviewer."},
        )

        self.assertTrue(response.json()["success"])

        self.create_change.refresh_from_db()
        self.assertEqual(
            self.create_change.after["description"],
            "Edited by a human reviewer.",
        )
        self.assertEqual(self.create_change.proposal_id, self.ai_proposal.id)

        self.ai_proposal.refresh_from_db()
        self.assertEqual(self.ai_proposal.source, Proposal.Source.AI)

        # No second proposal was spawned for this edit.
        self.assertEqual(
            Proposal.objects.filter(model=self.model, created_by=self.user).count(),
            1,
        )

        # Canonical model state is untouched -- this entity still doesn't
        # exist outside the proposal.
        self.assertFalse(ObjectType.objects.filter(id=self.proposed_object_type_id).exists())


class ObjectTypeAttributeDefaultValueTests(TestCase):
    """
    The Default value control is datatype-aware; changing a Data Type
    goes through the existing per-field proposal/discard machinery.
    """

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

    def test_text_default_value_on_create(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Owner",
                "attribute_key": "owner",
                "attribute_data_type": "text",
                "attribute_default_value": "Finance Tech",
            },
        )

        self.assertTrue(response.json()["success"])
        change = ProposalChange.objects.get(target_type="AttributeDefinition")
        self.assertEqual(change.after["default_value"], "Finance Tech")

    def test_number_default_value_on_create(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Cost",
                "attribute_key": "cost",
                "attribute_data_type": "number",
                "attribute_default_value": "42",
            },
        )

        self.assertTrue(response.json()["success"])
        change = ProposalChange.objects.get(target_type="AttributeDefinition")
        self.assertEqual(change.after["default_value"], 42)

    def test_boolean_default_value_true_on_create(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Certified",
                "attribute_key": "certified",
                "attribute_data_type": "boolean",
                "attribute_default_value": "true",
            },
        )

        self.assertTrue(response.json()["success"])
        change = ProposalChange.objects.get(target_type="AttributeDefinition")
        self.assertIs(change.after["default_value"], True)

    def test_boolean_default_value_not_set_on_create(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Certified",
                "attribute_key": "certified",
                "attribute_data_type": "boolean",
                "attribute_default_value": "",
            },
        )

        self.assertTrue(response.json()["success"])
        change = ProposalChange.objects.get(target_type="AttributeDefinition")
        self.assertIsNone(change.after["default_value"])

    def test_date_default_value_on_create(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Launch date",
                "attribute_key": "launch_date",
                "attribute_data_type": "date",
                "attribute_default_value": "2024-01-15",
            },
        )

        self.assertTrue(response.json()["success"])
        change = ProposalChange.objects.get(target_type="AttributeDefinition")
        self.assertEqual(change.after["default_value"], "2024-01-15")

    def test_datetime_default_value_on_create(self):
        response = self.client.post(
            self.edit_url(),
            {
                "action": "create_attribute",
                "attribute_name": "Go live",
                "attribute_key": "go_live",
                "attribute_data_type": "datetime",
                "attribute_default_value": "2024-01-15T09:30",
            },
        )

        self.assertTrue(response.json()["success"])
        change = ProposalChange.objects.get(target_type="AttributeDefinition")
        self.assertEqual(change.after["default_value"], "2024-01-15T09:30")

    def test_data_type_change_on_existing_attribute_creates_proposal_change(self):
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
                "attribute_choices": json.dumps(["Proposed", "Approved", "Live"]),
            },
        )

        self.assertTrue(response.json()["success"])

        change = ProposalChange.objects.get(
            target_type="AttributeDefinition", target_id=attribute.id, after__field="data_type",
        )
        self.assertEqual(change.after["value"], "choice")

        attribute.refresh_from_db()
        self.assertEqual(attribute.data_type, AttributeDefinition.DataType.TEXT)

    def test_choice_to_text_discard_restores_original_data_type_choices_and_default(self):
        attribute = AttributeDefinition.objects.create(
            object_type=self.object_type,
            name="Status",
            key="status",
            data_type=AttributeDefinition.DataType.CHOICE,
            config={"choices": ["Proposed", "Approved", "Live"]},
            default_value="Proposed",
            is_active=True,
        )

        save_response = self.client.post(
            self.edit_url(),
            {
                "action": "save_attribute",
                "attribute_id": str(attribute.id),
                "attribute_name": "Status",
                "attribute_key": "status",
                "attribute_data_type": "text",
                "attribute_default_value": "New default",
            },
        )
        self.assertTrue(save_response.json()["success"])

        self.assertTrue(
            ProposalChange.objects.filter(
                target_type="AttributeDefinition", target_id=attribute.id, after__field="data_type",
            ).exists()
        )

        discard_response = self.client.post(
            self.edit_url(),
            {"action": "discard_attribute", "attribute_id": str(attribute.id)},
        )
        self.assertTrue(discard_response.json()["success"])

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="AttributeDefinition", target_id=attribute.id,
            ).exists()
        )

        get_response = self.client.get(self.edit_url())
        status_attribute = next(
            a for a in get_response.context["attributes"] if a.key == "status"
        )

        self.assertEqual(status_attribute.proposed_values["data_type"], "choice")
        self.assertEqual(
            status_attribute.proposed_values["config"]["choices"],
            ["Proposed", "Approved", "Live"],
        )
        self.assertEqual(status_attribute.proposed_values["default_value"], "Proposed")
