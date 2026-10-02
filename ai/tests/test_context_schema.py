from django.test import SimpleTestCase

from ai.services.context_schema import ContextPacket


class ContextPacketTests(SimpleTestCase):

    def test_context_packet_round_trips_to_dict_and_from_dict(self):
        packet = ContextPacket(
            intent="Do something.",
            model_id="11111111-1111-1111-1111-111111111111",
            model_name="Model",
            model_revision=3,
            byte_size=42,
        )

        data = packet.model_dump(mode="json")
        rebuilt = ContextPacket.model_validate(data)

        self.assertEqual(rebuilt, packet)

    def test_schema_version_is_stamped(self):
        packet = ContextPacket(
            intent="x", model_id="id", model_name="M", model_revision=1, byte_size=0
        )

        self.assertEqual(packet.schema_version, "1.0")

    def test_truncated_defaults_false(self):
        packet = ContextPacket(
            intent="x", model_id="id", model_name="M", model_revision=1, byte_size=0
        )

        self.assertFalse(packet.truncated)

    def test_model_is_empty_defaults_false(self):
        packet = ContextPacket(
            intent="x", model_id="id", model_name="M", model_revision=1, byte_size=0
        )

        self.assertFalse(packet.model_is_empty)
