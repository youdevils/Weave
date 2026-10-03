from django.utils import timezone
from datetime import timedelta

from model.models.proposal import Proposal, ProposalChange

from assisted.models import AssistedTask
from assisted.services.activity import active_tasks_by_model_id, recent_tasks_for_workspace
from assisted.tests.support import AssistedTestCase


class RecentTasksForWorkspaceTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        task = AssistedTask.objects.create(**kwargs)
        if "created_at" in kwargs:
            AssistedTask.objects.filter(pk=task.pk).update(created_at=kwargs["created_at"])
            task.refresh_from_db()
        return task

    def test_recent_task_within_window_is_included(self):
        task = self.make_task(status=AssistedTask.Status.COMPLETED)

        results = list(recent_tasks_for_workspace(self.workspace, since=timezone.now() - timedelta(days=30)))

        self.assertEqual([t.id for t in results], [task.id])

    def test_old_terminal_task_outside_window_is_excluded(self):
        old = timezone.now() - timedelta(days=45)
        self.make_task(status=AssistedTask.Status.COMPLETED, created_at=old)

        results = list(recent_tasks_for_workspace(self.workspace, since=timezone.now() - timedelta(days=30)))

        self.assertEqual(results, [])

    def test_old_active_task_is_still_included(self):
        old = timezone.now() - timedelta(days=45)
        task = self.make_task(status=AssistedTask.Status.RUNNING, created_at=old)

        results = list(recent_tasks_for_workspace(self.workspace, since=timezone.now() - timedelta(days=30)))

        self.assertEqual([t.id for t in results], [task.id])

    def test_change_count_is_annotated_from_linked_proposal(self):
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
        task = self.make_task(status=AssistedTask.Status.READY_FOR_REVIEW, proposal=proposal)

        result = recent_tasks_for_workspace(self.workspace, since=timezone.now() - timedelta(days=30)).get(
            id=task.id
        )

        self.assertEqual(result.change_count, 1)

    def test_change_count_is_zero_without_a_proposal(self):
        task = self.make_task(status=AssistedTask.Status.FAILED)

        result = recent_tasks_for_workspace(self.workspace, since=timezone.now() - timedelta(days=30)).get(
            id=task.id
        )

        self.assertEqual(result.change_count, 0)


class ActiveTasksByModelIdTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        return AssistedTask.objects.create(**kwargs)

    def test_active_task_is_keyed_by_model_id(self):
        task = self.make_task(status=AssistedTask.Status.RUNNING)

        result = active_tasks_by_model_id([task])

        self.assertEqual(result, {self.model.id: task})

    def test_terminal_task_is_excluded(self):
        task = self.make_task(status=AssistedTask.Status.COMPLETED)

        result = active_tasks_by_model_id([task])

        self.assertEqual(result, {})
