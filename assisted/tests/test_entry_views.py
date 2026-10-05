from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from account.models import CustomUser
from assisted.models import AssistedTask, AssistedTaskEvidence
from assisted.tests.support import AssistedTestCase


class ReconcileEntryViewTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()
        # Reconcile requires something to reconcile against -- most tests in
        # this class don't reach that check (blocked earlier by role/blank
        # intent), but the ones that do need a non-empty Model.
        self.make_object_type(self.model)

    def url(self):
        return reverse("assisted:reconcile", args=[self.model.id])

    def test_get_renders_form(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start reconciliation")

    def test_blank_intent_is_rejected_and_persists_nothing(self):
        self.client.force_login(self.owner)

        response = self.client.post(self.url(), {"intent": "   "})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "before starting")
        self.assertEqual(AssistedTask.objects.count(), 0)

    def test_valid_submit_creates_a_queued_task_and_redirects_to_task_detail(self):
        self.client.force_login(self.owner)
        files = [SimpleUploadedFile("notes.txt", b"Process X is now Active.")]

        with patch("assisted.tasks.run_assisted_operation.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self.url(),
                    {"intent": "These documents show the latest status.", "evidence": files},
                    follow=True,
                )

        self.assertEqual(response.status_code, 200)
        task = AssistedTask.objects.get()
        self.assertEqual(task.operation, AssistedTask.Operation.RECONCILE)
        self.assertEqual(task.model_id, self.model.id)
        self.assertEqual(AssistedTaskEvidence.objects.filter(task=task).count(), 1)
        # Not assisted:task_detail -- that 404s while the task is still
        # active, by design (see assisted.views.task_detail).
        self.assertRedirects(response, reverse("assisted:landing", args=[self.model.id]))
        mock_delay.assert_called_once_with(str(task.id))

    def test_submit_without_evidence_is_rejected_and_persists_nothing(self):
        self.client.force_login(self.owner)

        response = self.client.post(self.url(), {"intent": "These documents show the latest status."})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attach at least one supporting document")
        self.assertEqual(AssistedTask.objects.count(), 0)

    def test_submit_against_an_empty_model_is_rejected(self):
        empty_model = self.make_model(name="Empty Model")
        self.client.force_login(self.owner)
        files = [SimpleUploadedFile("notes.txt", b"Something.")]

        response = self.client.post(
            reverse("assisted:reconcile", args=[empty_model.id]),
            {"intent": "Anything.", "evidence": files},
            follow=True,
        )

        self.assertRedirects(response, reverse("assisted:landing", args=[empty_model.id]))
        self.assertContains(response, "no structure yet to reconcile against")
        self.assertEqual(AssistedTask.objects.count(), 0)

    def test_a_second_submission_while_one_is_active_is_rejected(self):
        self.client.force_login(self.owner)
        files = [SimpleUploadedFile("notes.txt", b"Something.")]

        with patch("assisted.tasks.run_assisted_operation.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    self.url(), {"intent": "First.", "evidence": files}, follow=True
                )

        with patch("assisted.tasks.run_assisted_operation.delay"):
            response = self.client.post(
                self.url(), {"intent": "Second.", "evidence": files}, follow=True
            )

        self.assertRedirects(response, reverse("assisted:landing", args=[self.model.id]))
        self.assertEqual(AssistedTask.objects.filter(model=self.model).count(), 1)

    def test_viewer_gets_403_on_get(self):
        self.client.force_login(self.viewer)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 403)

    def test_viewer_gets_403_on_post(self):
        self.client.force_login(self.viewer)

        response = self.client.post(self.url(), {"intent": "Anything"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(AssistedTask.objects.count(), 0)

    def test_non_member_gets_404(self):
        self.client.force_login(self.stranger)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 404)

    def test_owner_without_the_assisted_entitlement_still_gets_403(self):
        """
        The landing page now hides these entry points for a plan without
        Assisted Work (see LandingViewEntitlementTests), but the entry views
        themselves must keep rejecting a direct hit regardless -- a user must
        never reach real Assisted Work execution through a guessed/bookmarked
        URL just because the UI stopped linking to it.
        """
        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])
        self.client.force_login(self.owner)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 403)


class ChangeAndAssessEntryViewTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def test_change_get_renders_form(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("assisted:change", args=[self.model.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start change")

    def test_change_valid_submit_shows_stub_message_and_persists_nothing(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("assisted:change", args=[self.model.id]),
            {"intent": "Rename this object type."},
            follow=True,
        )

        self.assertRedirects(response, reverse("assisted:landing", args=[self.model.id]))
        self.assertEqual(AssistedTask.objects.count(), 0)

    def test_assess_get_renders_form(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("assisted:assess", args=[self.model.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start assessment")

    def test_assess_valid_submit_shows_stub_message_and_persists_nothing(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("assisted:assess", args=[self.model.id]),
            {"intent": "Check for orphaned objects."},
            follow=True,
        )

        self.assertRedirects(response, reverse("assisted:landing", args=[self.model.id]))
        self.assertEqual(AssistedTask.objects.count(), 0)

    def test_change_viewer_gets_403(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("assisted:change", args=[self.model.id]))

        self.assertEqual(response.status_code, 403)

    def test_assess_viewer_gets_403(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("assisted:assess", args=[self.model.id]))

        self.assertEqual(response.status_code, 403)
