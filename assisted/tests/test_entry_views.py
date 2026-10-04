from django.urls import reverse

from assisted.models import AssistedTask, AssistedTaskEvidence
from assisted.tests.support import AssistedTestCase


class ReconcileEntryViewTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

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

    def test_valid_submit_shows_stub_message_and_persists_nothing(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            self.url(),
            {"intent": "These documents show the latest status."},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("assisted:landing", args=[self.model.id]))
        self.assertContains(response, "isn&#x27;t available yet")
        self.assertEqual(AssistedTask.objects.count(), 0)
        self.assertEqual(AssistedTaskEvidence.objects.count(), 0)

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
