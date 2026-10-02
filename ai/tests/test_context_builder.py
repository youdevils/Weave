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

    def test_model_is_empty_true_for_a_fresh_model_with_no_ontology(self):
        empty_model = self.make_model(name="Empty Model")

        packet = build_context_packet(model=empty_model, intent=self.intent)

        self.assertTrue(packet.model_is_empty)

    def test_model_is_empty_false_once_an_object_type_exists(self):
        packet = build_context_packet(model=self.model, intent=self.intent)

        self.assertFalse(packet.model_is_empty)

    def test_expansion_retains_unrelated_base_content_when_room_allows(self):
        # The old (buggy) behaviour replaced the base context with ONLY the
        # hop-reachable set the moment any expansion seed was present,
        # losing unrelated-but-relevant base content even when there was no
        # size pressure requiring that loss.
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        a = self.make_object(self.model, self.object_type, name="A")
        b = self.make_object(self.model, self.object_type, name="B")
        self.make_relationship(self.model, relationship_type, a, b)
        c = self.make_object(self.model, self.object_type, name="C")
        d = self.make_object(self.model, self.object_type, name="D")

        with override_settings(AI_CONTEXT_MAX_OBJECTS=300, AI_CONTEXT_MAX_HOPS=1, AI_CONTEXT_MAX_BYTES=10_000_000):
            packet = build_context_packet(
                model=self.model,
                intent=self.intent,
                expansion_state=ExpansionState(seed_object_ids=frozenset({str(a.id)})),
            )

        object_ids = {obj["id"] for obj in packet.objects}
        self.assertEqual(object_ids, {str(a.id), str(b.id), str(c.id), str(d.id)})

    def test_expansion_does_not_evict_base_when_ceiling_binds(self):
        # Five "hub" objects connected in a cycle (degree 2 each) always
        # outrank a lone, unconnected "seed"/"neighbour" pair (degree 1
        # each) under the existing degree-based ranking, so with the
        # ceiling set to exactly 5 the no-seed base is deterministically
        # the five hubs.
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        hubs = [self.make_object(self.model, self.object_type, name=f"Hub {i}") for i in range(5)]
        for i in range(5):
            self.make_relationship(self.model, relationship_type, hubs[i], hubs[(i + 1) % 5])

        seed = self.make_object(self.model, self.object_type, name="Seed")
        neighbour = self.make_object(self.model, self.object_type, name="Neighbour")
        self.make_relationship(self.model, relationship_type, seed, neighbour)

        hub_ids = {str(h.id) for h in hubs}

        with override_settings(AI_CONTEXT_MAX_OBJECTS=5, AI_CONTEXT_MAX_HOPS=1, AI_CONTEXT_MAX_BYTES=10_000_000):
            base_packet = build_context_packet(model=self.model, intent=self.intent)
            expanded_packet = build_context_packet(
                model=self.model,
                intent=self.intent,
                expansion_state=ExpansionState(seed_object_ids=frozenset({str(seed.id)})),
            )

        self.assertEqual({obj["id"] for obj in base_packet.objects}, hub_ids)
        self.assertTrue(base_packet.truncated)

        # Every hub survives the expansion cycle (base is never evicted);
        # the ceiling still binds, so the new seed/neighbour pair has no
        # room left to be added.
        self.assertEqual({obj["id"] for obj in expanded_packet.objects}, hub_ids)
        self.assertTrue(expanded_packet.truncated)

    def test_full_packet_respects_configured_byte_ceiling(self):
        from publication.services.bundle import canonical_json

        for index in range(10):
            self.make_object(self.model, self.object_type, name=f"Widget {index}")

        small_assets = [{"name": "a.txt", "content": "x", "mime_type": "text/plain"}]
        large_assets = [{"name": "a.txt", "content": "x" * 1500, "mime_type": "text/plain"}]

        with override_settings(AI_CONTEXT_MAX_BYTES=5500, AI_CONTEXT_MAX_OBJECTS=300, AI_CONTEXT_MAX_HOPS=2):
            small_packet = build_context_packet(model=self.model, intent=self.intent, assets=small_assets)
            large_packet = build_context_packet(model=self.model, intent=self.intent, assets=large_assets)
            large_size = len(canonical_json(large_packet.model_dump(mode="json")).encode("utf-8"))

        # A larger fixed-overhead section (assets, here) leaves less budget
        # for objects/relationships -- the ceiling applies to the whole
        # packet, not just that one subsection. (Overhead alone stays well
        # under the configured ceiling in both cases here, so this exercises
        # ordinary trimming rather than the documented "overhead alone
        # exceeds the ceiling" edge case.)
        self.assertLess(len(large_packet.objects), len(small_packet.objects))
        self.assertTrue(large_packet.truncated)
        self.assertLessEqual(large_size, 5500)
