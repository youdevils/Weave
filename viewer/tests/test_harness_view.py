from django.test import TestCase, override_settings
from django.urls import reverse


class HarnessViewTests(TestCase):
    def harness_url(self):
        return reverse("viewer:harness")

    @override_settings(DEBUG=True)
    def test_harness_available_in_debug(self):
        response = self.client.get(self.harness_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="weave-viewer-payload"')
        self.assertContains(response, "vis-network.min.js")
        self.assertContains(response, "weave-viewer.js")

    @override_settings(DEBUG=False)
    def test_harness_not_found_outside_debug(self):
        response = self.client.get(self.harness_url())

        self.assertEqual(response.status_code, 404)

    @override_settings(DEBUG=True)
    def test_harness_embeds_sample_payload_schema_version(self):
        response = self.client.get(self.harness_url())

        self.assertContains(response, "schema_version")
        self.assertContains(response, "1.0")
