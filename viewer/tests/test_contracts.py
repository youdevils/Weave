from django.test import SimpleTestCase

from viewer.contracts import (
    EdgeStyle,
    HierarchicalLayoutConfig,
    InteractionConfig,
    LayoutConfig,
    NodeStyle,
    PhysicsConfig,
    StabilisationConfig,
    ViewerConfig,
    ViewerEdge,
    ViewerMetadata,
    ViewerNode,
    ViewerPayload,
    validate_payload,
)


def _make_valid_payload() -> ViewerPayload:
    return ViewerPayload(
        schema_version="1.0",
        nodes=[
            ViewerNode(id="n1", type_key="type.a", label="Node 1", style=NodeStyle(shape="box")),
            ViewerNode(id="n2", type_key="type.b", label="Node 2"),
        ],
        edges=[
            ViewerEdge(id="e1", relationship_type_key="rel.a", source="n1", target="n2"),
        ],
    )


class PayloadRoundTripTests(SimpleTestCase):
    def test_to_dict_from_dict_round_trip(self):
        payload = _make_valid_payload()
        payload.viewer_config.layout.mode = "hierarchical"
        payload.viewer_config.physics.enabled = False

        restored = ViewerPayload.from_dict(payload.to_dict())

        self.assertEqual(restored.to_dict(), payload.to_dict())

    def test_to_dict_is_json_serialisable_shape(self):
        payload = _make_valid_payload()
        data = payload.to_dict()

        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(data["nodes"][0]["style"]["shape"], "box")
        self.assertEqual(data["edges"][0]["source"], "n1")


class MutableDefaultIndependenceTests(SimpleTestCase):
    """Regression guard: mutable dataclass defaults must use default_factory,
    never a shared instance, or independent objects would alias each other."""

    def test_node_data_dicts_are_independent(self):
        a = ViewerNode(id="a", type_key="t", label="A")
        b = ViewerNode(id="b", type_key="t", label="B")

        a.data["x"] = 1

        self.assertEqual(b.data, {})

    def test_node_style_instances_are_independent(self):
        a = ViewerNode(id="a", type_key="t", label="A")
        b = ViewerNode(id="b", type_key="t", label="B")

        a.style.shape = "box"

        self.assertIsNone(b.style.shape)

    def test_payload_node_lists_are_independent(self):
        a = ViewerPayload(schema_version="1.0")
        b = ViewerPayload(schema_version="1.0")

        a.nodes.append(ViewerNode(id="x", type_key="t", label="X"))

        self.assertEqual(b.nodes, [])

    def test_viewer_config_instances_are_independent(self):
        a = ViewerPayload(schema_version="1.0")
        b = ViewerPayload(schema_version="1.0")

        a.viewer_config.physics.enabled = False

        self.assertTrue(b.viewer_config.physics.enabled)


class ValidatePayloadValidTests(SimpleTestCase):
    def test_valid_payload_has_no_errors(self):
        self.assertEqual(validate_payload(_make_valid_payload()), [])

    def test_valid_payload_with_hierarchical_layout_has_no_errors(self):
        payload = _make_valid_payload()
        payload.viewer_config = ViewerConfig(
            layout=LayoutConfig(mode="hierarchical", hierarchical=HierarchicalLayoutConfig(direction="LR", sort_method="directed")),
            physics=PhysicsConfig(enabled=False, stabilisation=StabilisationConfig(enabled=False)),
            interaction=InteractionConfig(hover=True),
        )

        self.assertEqual(validate_payload(payload), [])


class ValidatePayloadInvalidTests(SimpleTestCase):
    def test_unsupported_schema_version(self):
        payload = _make_valid_payload()
        payload.schema_version = "99.0"

        errors = validate_payload(payload)

        self.assertTrue(any("schema_version" in e for e in errors))

    def test_duplicate_node_ids(self):
        payload = _make_valid_payload()
        payload.nodes.append(ViewerNode(id="n1", type_key="type.a", label="Duplicate"))

        errors = validate_payload(payload)

        self.assertTrue(any("duplicate node ids" in e for e in errors))

    def test_empty_node_id(self):
        payload = _make_valid_payload()
        payload.nodes.append(ViewerNode(id="", type_key="type.a", label="Empty id"))

        errors = validate_payload(payload)

        self.assertTrue(any("empty id" in e for e in errors))

    def test_duplicate_edge_ids(self):
        payload = _make_valid_payload()
        payload.edges.append(ViewerEdge(id="e1", relationship_type_key="rel.a", source="n1", target="n2"))

        errors = validate_payload(payload)

        self.assertTrue(any("duplicate edge ids" in e for e in errors))

    def test_edge_with_dangling_source(self):
        payload = _make_valid_payload()
        payload.edges.append(ViewerEdge(id="e2", relationship_type_key="rel.a", source="missing", target="n2"))

        errors = validate_payload(payload)

        self.assertTrue(any("does not reference an existing node" in e and "source" in e for e in errors))

    def test_edge_with_dangling_target(self):
        payload = _make_valid_payload()
        payload.edges.append(ViewerEdge(id="e2", relationship_type_key="rel.a", source="n1", target="missing"))

        errors = validate_payload(payload)

        self.assertTrue(any("does not reference an existing node" in e and "target" in e for e in errors))

    def test_unknown_layout_mode(self):
        payload = _make_valid_payload()
        payload.viewer_config.layout.mode = "not-a-real-mode"

        errors = validate_payload(payload)

        self.assertTrue(any("unknown layout mode" in e for e in errors))

    def test_unknown_hierarchical_direction(self):
        payload = _make_valid_payload()
        payload.viewer_config.layout.hierarchical.direction = "sideways"

        errors = validate_payload(payload)

        self.assertTrue(any("unknown hierarchical direction" in e for e in errors))

    def test_unknown_hierarchical_sort_method(self):
        payload = _make_valid_payload()
        payload.viewer_config.layout.hierarchical.sort_method = "random"

        errors = validate_payload(payload)

        self.assertTrue(any("unknown hierarchical sort_method" in e for e in errors))


class StyleContractTests(SimpleTestCase):
    def test_node_style_extra_round_trips_but_is_just_data(self):
        style = NodeStyle(shape="box", extra={"future_field": "value"})

        self.assertEqual(style.to_dict()["extra"], {"future_field": "value"})

    def test_edge_style_uses_british_colour_spelling(self):
        style = EdgeStyle(colour="#000000")

        self.assertIn("colour", style.to_dict())
        self.assertNotIn("color", style.to_dict())

    def test_node_style_image_is_optional_and_round_trips(self):
        self.assertIsNone(NodeStyle().image)

        payload = _make_valid_payload()
        payload.nodes[0].style.image = "data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C%2Fsvg%3E"
        payload.nodes[0].style.shape = "circularImage"

        restored = ViewerPayload.from_dict(payload.to_dict())

        self.assertEqual(restored.nodes[0].style.image, payload.nodes[0].style.image)
        self.assertIsNone(restored.nodes[1].style.image)
        self.assertEqual(validate_payload(restored), [])

    def test_payload_without_image_key_still_loads(self):
        data = _make_valid_payload().to_dict()
        for node in data["nodes"]:
            node["style"].pop("image", None)

        self.assertEqual(validate_payload(ViewerPayload.from_dict(data)), [])
