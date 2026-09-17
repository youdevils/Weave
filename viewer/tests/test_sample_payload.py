from django.test import SimpleTestCase

from viewer.contracts import validate_payload
from viewer.services.sample_payload import build_sample_payload


class SamplePayloadTests(SimpleTestCase):
    def test_sample_payload_is_valid(self):
        payload = build_sample_payload()

        self.assertEqual(validate_payload(payload), [])

    def test_sample_payload_has_nodes_and_edges(self):
        payload = build_sample_payload()

        self.assertGreater(len(payload.nodes), 0)
        self.assertGreater(len(payload.edges), 0)

    def test_sample_payload_round_trips_through_dict(self):
        from viewer.contracts import ViewerPayload

        payload = build_sample_payload()
        restored = ViewerPayload.from_dict(payload.to_dict())

        self.assertEqual(restored.to_dict(), payload.to_dict())
