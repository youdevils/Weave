from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import CustomUser
from model.models.model import Model
from workspace.models import Workspace, WorkspaceMember

from assisted.models import AssistedTask


class DashboardAssistedActivityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.owner.email_verified = True
        cls.owner.save(update_fields=["email_verified"])

        WorkspaceMember.objects.create(
            workspace=cls.workspace, user=cls.owner, role=WorkspaceMember.Role.OWNER
        )

        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model")

    def setUp(self):
        self.client.force_login(self.owner)

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        task = AssistedTask.objects.create(**kwargs)
        if "created_at" in kwargs:
            AssistedTask.objects.filter(pk=task.pk).update(created_at=kwargs["created_at"])
        return task

    def url(self):
        return reverse("workspace:index")

    def test_no_assisted_history_shows_empty_state(self):
        response = self.client.get(self.url())

        self.assertContains(response, "No assisted activity yet")

    def test_recent_task_is_shown_in_sidebar(self):
        self.make_task(status=AssistedTask.Status.COMPLETED)

        response = self.client.get(self.url())

        self.assertEqual(len(response.context["assisted_activity"]), 1)
        self.assertContains(response, "Assisted activity")
        self.assertContains(response, "Test Model")

    def test_old_terminal_task_is_excluded_from_sidebar(self):
        self.make_task(
            status=AssistedTask.Status.COMPLETED,
            created_at=timezone.now() - timedelta(days=45),
        )

        response = self.client.get(self.url())

        self.assertEqual(list(response.context["assisted_activity"]), [])

    def test_old_active_task_still_shown_in_sidebar(self):
        task = self.make_task(
            status=AssistedTask.Status.RUNNING,
            created_at=timezone.now() - timedelta(days=45),
        )

        response = self.client.get(self.url())

        self.assertEqual([t.id for t in response.context["assisted_activity"]], [task.id])

    def test_model_card_shows_in_progress_badge_for_running_task(self):
        self.make_task(status=AssistedTask.Status.RUNNING)

        response = self.client.get(self.url())

        self.assertContains(response, "In progress")

    def test_model_card_shows_ready_for_review_badge(self):
        self.make_task(status=AssistedTask.Status.READY_FOR_REVIEW)

        response = self.client.get(self.url())

        self.assertContains(response, "Ready for review")

    def test_model_card_shows_no_badge_without_active_task(self):
        self.make_task(status=AssistedTask.Status.COMPLETED)

        response = self.client.get(self.url())

        self.assertNotContains(response, "In progress")
        self.assertNotContains(response, "Ready for review")
