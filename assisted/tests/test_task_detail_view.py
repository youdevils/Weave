from django.urls import reverse

from account.models import CustomUser
from model.models.proposal import Proposal, ProposalChange
from workspace.models import Workspace, WorkspaceMember

from assisted.models import AssistedTask
from assisted.tests.support import AssistedTestCase


class TaskDetailViewTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.RECONCILE)
        kwargs.setdefault("model", self.model)
        kwargs.setdefault("submitted_intent", "Reconcile the latest status update.")
        return AssistedTask.objects.create(**kwargs)

    def url(self, task):
        return reverse("assisted:task_detail", args=[self.model.id, task.id])

    def test_proposal_branch_shows_change_count_and_review_link(self):
        proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.owner,
            source=Proposal.Source.AI,
            status=Proposal.Status.COMPLETED,
        )
        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.AI,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id="11111111-1111-1111-1111-111111111111",
            after={"name": "Widget"},
        )
        task = self.make_task(status=AssistedTask.Status.COMPLETED, proposal=proposal)
        self.client.force_login(self.owner)

        response = self.client.get(self.url(task))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 proposed change")
        self.assertContains(response, reverse("model:proposal", args=[self.model.id, proposal.id]))

    def test_no_proposal_branch_shows_failure_reason(self):
        task = self.make_task(
            status=AssistedTask.Status.FAILED,
            failure_reason="OnyxJar could not complete this operation.",
        )
        self.client.force_login(self.owner)

        response = self.client.get(self.url(task))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OnyxJar could not complete this operation.")

    def test_assess_shows_aspirational_non_link_copy(self):
        task = self.make_task(
            operation=AssistedTask.Operation.ASSESS,
            status=AssistedTask.Status.COMPLETED,
        )
        self.client.force_login(self.owner)

        response = self.client.get(self.url(task))

        self.assertContains(response, "Assessment available")
        self.assertNotContains(response, "View assessment")

    def test_active_task_returns_404(self):
        task = self.make_task(status=AssistedTask.Status.RUNNING)
        self.client.force_login(self.owner)

        response = self.client.get(self.url(task))

        self.assertEqual(response.status_code, 404)

    def test_non_member_gets_404(self):
        task = self.make_task(status=AssistedTask.Status.COMPLETED)

        other_workspace = Workspace.objects.create(name="Other Workspace")
        outsider = CustomUser.objects.create_user(email="outsider2@example.com", password="pw")
        WorkspaceMember.objects.create(
            workspace=other_workspace,
            user=outsider,
            role=WorkspaceMember.Role.OWNER,
        )
        self.client.force_login(outsider)

        response = self.client.get(self.url(task))

        self.assertEqual(response.status_code, 404)
