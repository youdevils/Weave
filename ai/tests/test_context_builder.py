from django.test import override_settings

from ai.services.context_builder import build_context_packet
from ai.services.context_expansion import ExpansionState
from ai.services.intent import validate_intent
from ai.tests.support import AIServiceTestCase


class BuildContextPacketTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model(purpose="Track widgets.", scope="Widgets only.", exclusions="No gadgets.")
        self.object_type = self.make_object_type(self.model, key="widget")
        self.intent = validate_intent("Describe the model.")

    def test_includes_model_purpose_scope_exclusions_and_revision(self):
        packet = build_context_packet(model=self.model, intent=self.intent)

        self.assertEqual(packet.model_purpose, "Track widgets.")
        self.assertEqual(packet.model_scope, "Widgets only.")
        self.assertEqual(packet.model_exclusions, "No gadgets.")
        self.assertEqual(packet.model_revision, self.model.revision)

    def test_includes_ontology_slice(self):
        packet = build_context_packet(model=self.model, intent=self.intent)

        node_ids = {node["id"] for node in packet.ontology.get("nodes", [])}
        self.assertIn(str(self.object_type.id), node_ids)

    def test_includes_supplied_assets(self):
        assets = [{"name": "spec.txt", "content": "Some content.", "mime_type": "text/plain"}]

        packet = build_context_packet(model=self.model, intent=self.intent, assets=assets)

        self.assertEqual(packet.assets, assets)

    def test_includes_previous_attempt_issues(self):
        from model.services.validation.result import ValidationIssue

        issues = [ValidationIssue(code="bad", message="Bad thing.")]

        packet = build_context_packet(model=self.model, intent=self.intent, previous_issues=issues)

        self.assertEqual(packet.previous_attempt_issues[0]["code"], "bad")

    @override_settings(AI_CONTEXT_MAX_OBJECTS=2, AI_CONTEXT_MAX_HOPS=2, AI_CONTEXT_MAX_BYTES=10_000_000)
    def test_initial_context_bounded_by_ai_context_max_objects(self):
        for index in range(5):
            self.make_object(self.model, self.object_type, name=f"Widget {index}")

        packet = build_context_packet(model=self.model, intent=self.intent)

        self.assertLessEqual(len(packet.objects), 2)
        self.assertTrue(packet.truncated)

    def test_initial_context_not_truncated_when_within_limits(self):
        self.make_object(self.model, self.object_type, name="Widget 1")

        packet = build_context_packet(model=self.model, intent=self.intent)

        self.assertFalse(packet.truncated)

    def test_byte_size_reflects_serialised_packet(self):
        packet = build_context_packet(model=self.model, intent=self.intent)

        self.assertGreater(packet.byte_size, 0)

    def test_expansion_seeds_bound_neighbourhood_via_hops(self):
        center = self.make_object(self.model, self.object_type, name="Center")
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        neighbour = self.make_object(self.model, self.object_type, name="Neighbour")
        far = self.make_object(self.model, self.object_type, name="Far")
        self.make_relationship(self.model, relationship_type, center, neighbour)
        self.make_relationship(self.model, relationship_type, neighbour, far)

        with override_settings(AI_CONTEXT_MAX_HOPS=1, AI_CONTEXT_MAX_OBJECTS=300, AI_CONTEXT_MAX_BYTES=10_000_000):
            packet = build_context_packet(
                model=self.model,
                intent=self.intent,
                expansion_state=ExpansionState(seed_object_ids=frozenset({str(center.id)})),
            )

        object_ids = {obj["id"] for obj in packet.objects}
        self.assertIn(str(center.id), object_ids)
        self.assertIn(str(neighbour.id), object_ids)
        self.assertNotIn(str(far.id), object_ids)
