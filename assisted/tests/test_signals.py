import uuid

from django.test import TransactionTestCase, override_settings

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace, WorkspaceMember

from assisted.models import AssistedTask


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class ProposalSignalTests(TransactionTestCase):
    """
    TransactionTestCase (not TestCase): submission.process()'s
    transaction.on_commit-dispatched queue-drain only fires on a real
    commit, matching
    model.services.model_template.tests.test_template_appearance_full_survival's
    use of the same override.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Test Workspace")
        self.user = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.user, role=WorkspaceMember.Role.OWNER
        )
        self.model = Model.objects.create(workspace=self.workspace, name="Test Model")
        self.object_type = ObjectType.objects.create(model=self.model, name="Widget", key="widget")

    def make_task(self, proposal):
        return AssistedTask.objects.create(
            workspace=self.workspace,
            creator=self.user,
            operation=AssistedTask.Operation.CREATE,
            model=self.model,
            proposal=proposal,
            status=AssistedTask.Status.READY_FOR_REVIEW,
            submitted_intent="Track widgets.",
        )

    def make_ready_proposal(self):
        proposal = ProposalService.create_working(self.model, self.user, source=Proposal.Source.AI)
        ProposalService.record_changes_bulk(
            proposal=proposal,
            specs=[
                {
                    "operation": "create",
                    "target_type": "Object",
                    "target_id": uuid.uuid4(),
                    "parent_type": "ObjectType",
                    "parent_id": self.object_type.id,
                    "before": None,
                    "after": {"name": "Widget 1", "description": "", "is_active": True, "attributes": {}},
                }
            ],
        )
        return proposal

    def test_submitting_the_proposal_completes_the_task(self):
        proposal = self.make_ready_proposal()
        task = self.make_task(proposal)

        ProposalService.submit(proposal)

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.COMPLETED)
        self.assertIsNotNone(task.completed_at)

    def test_abandoning_the_proposal_fails_the_task(self):
        proposal = self.make_ready_proposal()
        task = self.make_task(proposal)

        ProposalService.abandon(proposal)

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.PROPOSAL_ABANDONED)
        self.assertIsNone(task.proposal)

    def test_a_proposal_with_no_assisted_task_is_unaffected(self):
        proposal = self.make_ready_proposal()

        # Must not raise even though no AssistedTask references this Proposal.
        ProposalService.submit(proposal)
