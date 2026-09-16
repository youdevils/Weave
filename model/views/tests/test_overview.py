from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from workspace.models import Workspace, WorkspaceMember


class ModelNameEditingTests(TestCase):

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
        return reverse(
            "model:overview",
            args=[self.model.id],
        )

    def working_proposal(self):
        return Proposal.objects.get(
            model=self.model,
            created_by=self.user,
            source=Proposal.Source.USER,
            status=Proposal.Status.WORKING,
        )

    def test_save_name_records_proposal_change_without_mutating_canonical_model(self):
        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "Renamed Model",
            },
        )

        data = response.json()

        self.assertTrue(data["success"])
        self.assertTrue(data["proposed"])
        self.assertEqual(data["value"], "Renamed Model")

        self.model.refresh_from_db()
        self.assertEqual(self.model.name, "Test Model")

        change = ProposalChange.objects.get(
            target_type="Model",
            target_id=self.model.id,
            after__field="name",
        )
        self.assertEqual(change.operation, ProposalChange.Operation.UPDATE)
        self.assertEqual(change.after["value"], "Renamed Model")
        self.assertEqual(change.before["value"], "Test Model")

    def test_save_canonical_value_discards_existing_change(self):
        self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "Renamed Model",
            },
        )

        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "Test Model",
            },
        )

        data = response.json()

        self.assertTrue(data["success"])
        self.assertFalse(data["proposed"])

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="Model",
                target_id=self.model.id,
                after__field="name",
            ).exists()
        )

    def test_discard_action_removes_change(self):
        self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "Renamed Model",
            },
        )

        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "action": "discard",
            },
        )

        data = response.json()

        self.assertTrue(data["success"])
        self.assertFalse(data["proposed"])
        self.assertEqual(data["value"], "Test Model")

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="Model",
                target_id=self.model.id,
                after__field="name",
            ).exists()
        )

    def test_empty_name_is_rejected(self):
        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

        self.assertFalse(
            ProposalChange.objects.filter(
                target_type="Model",
                target_id=self.model.id,
                after__field="name",
            ).exists()
        )

    def test_overlong_name_is_rejected(self):
        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "x" * 201,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_get_renders_proposed_name_when_a_change_is_pending(self):
        self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "Renamed Model",
            },
        )

        response = self.client.get(self.overview_url())

        self.assertEqual(response.context["name_value"], "Renamed Model")
        self.assertTrue(response.context["name_proposed"])
        self.assertContains(response, "Renamed Model")

    def test_get_renders_canonical_name_when_no_change_is_pending(self):
        response = self.client.get(self.overview_url())

        self.assertEqual(response.context["name_value"], "Test Model")
        self.assertFalse(response.context["name_proposed"])


class OverviewSidebarRefreshTests(TestCase):

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
        return reverse(
            "model:overview",
            args=[self.model.id],
        )

    def test_successful_save_returns_refreshed_sidebar_html(self):
        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "Renamed Model",
            },
        )

        data = response.json()

        self.assertIn("sidebar_html", data)
        self.assertIn("model-sidebar", data["sidebar_html"])
        self.assertIn("model-nav-proposal", data["sidebar_html"])

    def test_failed_save_does_not_include_sidebar_html(self):
        response = self.client.post(
            self.overview_url(),
            {
                "field": "name",
                "value": "",
            },
        )

        data = response.json()

        self.assertNotIn("sidebar_html", data)
