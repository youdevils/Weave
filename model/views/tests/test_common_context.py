import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember


class CommonContextProposalStateTests(TestCase):

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

    def overview_url(self):
        return reverse("model:overview", args=[self.model.id])

    def test_active_proposal_ignores_a_stale_session_pointer(self):
        session = self.client.session
        session["active_proposals"] = {str(self.model.id): str(uuid.uuid4())}
        session.save()

        response = self.client.get(self.overview_url())

        self.assertIsNone(response.context["active_proposal"])

    def test_proposals_list_excludes_acknowledged_completed_but_includes_others(self):
        live_working = Proposal.objects.create(
            model=self.model, created_by=self.user, status=Proposal.Status.WORKING,
        )
        live_queued = Proposal.objects.create(
            model=self.model, created_by=self.user, status=Proposal.Status.QUEUED,
        )
        unacknowledged_completed = Proposal.objects.create(
            model=self.model, created_by=self.user, status=Proposal.Status.COMPLETED,
        )
        acknowledged_completed = Proposal.objects.create(
            model=self.model, created_by=self.user, status=Proposal.Status.COMPLETED,
            acknowledged_at=timezone.now(),
        )

        response = self.client.get(self.overview_url())

        listed_ids = {p.id for p in response.context["proposals"]}

        self.assertIn(live_working.id, listed_ids)
        self.assertIn(live_queued.id, listed_ids)
        self.assertIn(unacknowledged_completed.id, listed_ids)
        self.assertNotIn(acknowledged_completed.id, listed_ids)

    def test_failed_active_proposal_changes_are_overlaid_into_object_types(self):
        """
        Regression test: previously get_model_context only resolved a
        WORKING proposal for the effective/overlaid object type
        collections, silently ignoring a FAILED (but still editable
        and resubmittable) proposal's changes.
        """

        failed = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.FAILED,
        )

        ProposalChange.objects.create(
            proposal=failed,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type="ObjectType",
            target_id=self.object_type.id,
            after={"field": "name", "value": "Renamed While Failed"},
        )

        activate_proposal(self.client, self.model.id, failed)

        response = self.client.get(
            reverse("model:object_types", args=[self.model.id])
        )

        object_types = {ot.id: ot for ot in response.context["object_types"]}

        self.assertEqual(
            object_types[self.object_type.id].name,
            "Renamed While Failed",
        )
