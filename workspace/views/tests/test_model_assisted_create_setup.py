from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from workspace.models import Workspace, WorkspaceMember

from assisted.models import AssistedTask


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.owner = CustomUser.objects.create_user(email="owner@example.com", password="pw")
        cls.editor = CustomUser.objects.create_user(email="editor@example.com", password="pw")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="pw")
        cls.stranger = CustomUser.objects.create_user(email="stranger@example.com", password="pw")

        for user, role in (
            (cls.owner, WorkspaceMember.Role.OWNER),
            (cls.editor, WorkspaceMember.Role.EDITOR),
            (cls.viewer, WorkspaceMember.Role.VIEWER),
        ):
            WorkspaceMember.objects.create(workspace=cls.workspace, user=user, role=role)

    def setUp(self):
        self.model = Model.objects.create(workspace=self.workspace, name="M")

    def url(self, model=None):
        return reverse("workspace:model_assisted_create_setup", kwargs={"model_id": (model or self.model).id})


class RoleGateTests(Base):

    def test_owner_may_submit(self):
        self.client.force_login(self.owner)

        with patch("assisted.tasks.run_assisted_create.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url(), {"intent": "Track widgets."}, follow=True)

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 1)
        mock_delay.assert_called_once()

    def test_editor_may_submit(self):
        self.client.force_login(self.editor)

        with patch("assisted.tasks.run_assisted_create.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url(), {"intent": "Track widgets."}, follow=True)

        self.assertRedirects(response, reverse("workspace:index"))
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 1)

    def test_viewer_is_forbidden(self):
        self.client.force_login(self.viewer)

        response = self.client.post(self.url(), {"intent": "Track widgets."})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 0)

    def test_a_non_member_gets_404(self):
        self.client.force_login(self.stranger)

        response = self.client.post(self.url(), {"intent": "Track widgets."})

        self.assertEqual(response.status_code, 404)

    def test_anonymous_users_are_sent_to_log_in(self):
        response = self.client.post(self.url(), {"intent": "Track widgets."})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 0)


class SubmissionTests(Base):

    def setUp(self):
        super().setUp()
        self.client.force_login(self.owner)

    def test_get_renders_the_setup_form(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assisted creation")

    def test_blank_intent_re_renders_with_an_error(self):
        with patch("assisted.tasks.run_assisted_create.delay") as mock_delay:
            response = self.client.post(self.url(), {"intent": "   "})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 0)
        mock_delay.assert_not_called()

    @override_settings(ASSISTED_MAX_EVIDENCE_FILES=1)
    def test_too_many_files_re_renders_with_an_error(self):
        files = [SimpleUploadedFile("a.txt", b"one"), SimpleUploadedFile("b.txt", b"two")]

        with patch("assisted.tasks.run_assisted_create.delay") as mock_delay:
            response = self.client.post(self.url(), {"intent": "Track widgets.", "evidence": files})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 0)
        mock_delay.assert_not_called()

    def test_a_second_submission_while_one_is_active_is_rejected(self):
        with patch("assisted.tasks.run_assisted_create.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.url(), {"intent": "First."}, follow=True)

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url(), {"intent": "Second."}, follow=True)

        self.assertRedirects(
            response,
            reverse("workspace:model_starting_point", kwargs={"model_id": self.model.id}),
        )
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 1)

    def test_dispatch_only_follows_a_durable_commit(self):
        with patch("assisted.tasks.run_assisted_create.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.url(), {"intent": "Track widgets."})

        task = AssistedTask.objects.get(model=self.model)
        mock_delay.assert_called_once_with(str(task.id))
