from model.models.proposal import ProposalChange
from model.services.appearance import OBJECT_TYPE, RELATIONSHIP_TYPE, AppearanceService
from model.services.model_graph.compiler import compile_model_graph
from model.services.model_graph.explorer import explore
from viewer.contracts import ViewerPayload, validate_payload

from .base import ModelGraphTestCase

AMBER_BACKGROUND = "#FFF3BF"
AMBER = "#F08C00"


class CompilerTestCase(ModelGraphTestCase):

    def compile(self, proposal=None, **params):
        exploration = explore(self.model, proposal, params)
        payload = compile_model_graph(self.model, exploration.dataset, exploration.projection)
        self.assertEqual(validate_payload(payload), [])
        return payload

    def node(self, payload, obj):
        return next(n for n in payload.nodes if n.id == str(obj.id))

    def edge(self, payload, relationship):
        return next(e for e in payload.edges if e.id == str(relationship.id))

    def seed(self):
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.membership = self.make_relationship(self.alice, self.ops)


class PayloadContentTests(CompilerTestCase):

    def test_objects_and_relationships_become_nodes_and_edges(self):
        self.seed()
        payload = self.compile()

        self.assertEqual({n.id for n in payload.nodes}, {str(self.alice.id), str(self.ops.id)})
        self.assertEqual([e.id for e in payload.edges], [str(self.membership.id)])

    def test_edge_direction_is_subject_to_object(self):
        self.seed()
        edge = self.compile().edges[0]

        self.assertEqual((edge.source, edge.target), (str(self.alice.id), str(self.ops.id)))

    def test_node_carries_type_and_populated_attributes_only(self):
        self.seed()
        blank = self.make_object(self.person_type, "Blank", attributes={"status": ""})
        payload = self.compile()

        node = self.node(payload, self.alice)
        self.assertEqual(node.label, "Alice")
        self.assertEqual(node.type_key, "person")
        self.assertEqual(node.data["object_type_name"], "Person")
        self.assertEqual(node.data["attributes"], {"status": "Active"})
        self.assertEqual(self.node(payload, blank).data["attributes"], {})

    def test_duplicate_object_names_are_distinct_nodes(self):
        first = self.make_object(self.person_type, "Alice")
        second = self.make_object(self.person_type, "Alice")

        payload = self.compile()

        self.assertEqual({n.id for n in payload.nodes}, {str(first.id), str(second.id)})

    def test_edge_carries_type_and_relationship_attributes(self):
        AttributeDefinition = self.status_attribute.__class__
        AttributeDefinition.objects.create(
            relationship_type=self.member_of, name="Since", key="since", data_type="date"
        )
        self.seed()
        self.membership.attributes = {"since": "2022-01-01", "junk": "not defined"}
        self.membership.save()

        edge = self.compile().edges[0]

        self.assertEqual(edge.label, "Member of")
        self.assertEqual(edge.relationship_type_key, "member_of")
        self.assertEqual(edge.data["attributes"], {"since": "2022-01-01"})

    def test_inactive_objects_and_dangling_relationships_are_not_rendered(self):
        self.seed()
        gone = self.make_object(self.person_type, "Gone", is_active=False)
        self.make_relationship(gone, self.ops)

        payload = self.compile()

        self.assertNotIn(str(gone.id), {n.id for n in payload.nodes})
        self.assertEqual(len(payload.edges), 1)

    def test_empty_model_gives_a_valid_empty_payload(self):
        payload = self.compile()

        self.assertEqual((payload.nodes, payload.edges), ([], []))
        self.assertEqual(len(payload.node_types), 2)

    def test_model_with_only_inactive_objects_gives_an_empty_payload(self):
        self.make_object(self.person_type, "Ghost", is_active=False)

        self.assertEqual(self.compile().nodes, [])

    def test_payload_round_trips_through_the_contract(self):
        self.seed()
        payload = self.compile()

        self.assertEqual(validate_payload(ViewerPayload.from_dict(payload.to_dict())), [])

    def test_object_with_many_relationships(self):
        self.seed()
        for n in range(40):
            self.make_relationship(self.make_object(self.person_type, f"P{n}"), self.ops)

        payload = self.compile()

        self.assertEqual(len(payload.edges), 41)


class FilteredProjectionTests(CompilerTestCase):

    def test_hidden_object_type_removes_its_nodes_and_their_edges(self):
        self.seed()
        payload = self.compile(hide_objects=[str(self.team_type.id)])

        self.assertEqual([n.id for n in payload.nodes], [str(self.alice.id)])
        self.assertEqual(payload.edges, [])

    def test_hidden_relationship_type_keeps_the_nodes(self):
        self.seed()
        payload = self.compile(hide_relationships=[str(self.member_of.id)])

        self.assertEqual(len(payload.nodes), 2)
        self.assertEqual(payload.edges, [])

    def test_size_cap_drops_edges_to_removed_nodes(self):
        self.seed()
        payload = self.compile(limit="1")

        self.assertEqual(len(payload.nodes), 1)
        self.assertEqual(payload.edges, [])


class AppearanceInheritanceTests(CompilerTestCase):

    def test_default_look_matches_the_ontology_default(self):
        self.seed()
        style = self.node(self.compile(), self.alice).style

        self.assertEqual((style.shape, style.background, style.border), ("box", "#EDF2FF", "#4C6EF5"))

    def test_type_override_applies_to_every_object_of_the_type(self):
        self.seed()
        other = self.make_object(self.person_type, "Bob")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "shape", "square")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background", "#1c7ed6")

        payload = self.compile()

        for person in (self.alice, other):
            self.assertEqual(
                (self.node(payload, person).style.shape, self.node(payload, person).style.background),
                ("square", "#1C7ED6"),
            )
        self.assertEqual(self.node(payload, self.ops).style.shape, "box")

    def test_explorer_uses_exactly_the_appearance_the_service_resolves(self):
        self.seed()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "border", "#222222")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.member_of.id, "line_style", "dotted")

        payload = self.compile()

        resolved = AppearanceService.resolve_object_type(self.model, self.person_type.id)
        self.assertEqual(self.node(payload, self.alice).style.border, resolved.border)
        self.assertEqual(self.edge(payload, self.membership).style.dashes, [2, 4])

    def test_model_customisation_and_theme_reach_nodes_and_edges(self):
        self.seed()
        stack = "'Courier New', Courier, monospace"
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")
        AppearanceService.update_customisation(self.model, "theme", "font_family", stack)
        AppearanceService.update_customisation(self.model, "relationship", "arrows", "both")

        payload = self.compile()

        self.assertEqual(self.node(payload, self.alice).style.border, "#00AA00")
        self.assertEqual(self.node(payload, self.alice).style.font["face"], stack)
        self.assertEqual(self.edge(payload, self.membership).style.font["face"], stack)
        self.assertEqual(self.edge(payload, self.membership).style.arrows, "to, from")

    def test_canvas_background_is_exposed(self):
        AppearanceService.update_customisation(self.model, "theme", "canvas_background", "#101010")

        self.assertEqual(self.compile().viewer_config.extra["canvas_background"], "#101010")

    def test_type_icon_makes_an_image_node(self):
        self.seed()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "icon", "person")

        style = self.node(self.compile(), self.alice).style

        self.assertEqual(style.shape, "circularImage")
        self.assertTrue(style.image.startswith("data:image/svg+xml"))


class AttributeDrivenAppearanceTests(CompilerTestCase):
    """Colour resolved per-instance from an eligible attribute's value."""

    def setUp(self):
        super().setUp()
        AttributeDefinitionCls = self.status_attribute.__class__
        self.urgent_attribute = AttributeDefinitionCls.objects.create(
            object_type=self.person_type,
            name="Urgent",
            key="urgent",
            data_type=AttributeDefinitionCls.DataType.BOOLEAN,
        )
        self.importance_attribute = AttributeDefinitionCls.objects.create(
            relationship_type=self.member_of,
            name="Importance",
            key="importance",
            data_type=AttributeDefinitionCls.DataType.CHOICE,
            config={"choices": ["High", "Low"]},
        )

    def set_attribute_colour(self, kind, type_id, attribute_key, value_key, colour):
        AppearanceService.set_attribute_colour(self.model, kind, type_id, attribute_key, value_key, colour)

    def test_choice_value_drives_background_per_instance(self):
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        left = self.make_object(self.person_type, "Bob", attributes={"status": "Left"})
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_source", "attribute")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_attribute", "status")
        self.set_attribute_colour(OBJECT_TYPE, self.person_type.id, "status", "Active", "#00FF00")
        self.set_attribute_colour(OBJECT_TYPE, self.person_type.id, "status", "Left", "#FF0000")

        payload = self.compile()

        self.assertEqual(self.node(payload, self.alice).style.background, "#00FF00")
        self.assertEqual(self.node(payload, left).style.background, "#FF0000")

    def test_missing_or_unmapped_value_falls_back_to_the_type_colour(self):
        no_value = self.make_object(self.person_type, "NoValue")
        unmapped = self.make_object(self.person_type, "Unmapped", attributes={"status": "Other"})
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_source", "attribute")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_attribute", "status")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background", "#123456")
        self.set_attribute_colour(OBJECT_TYPE, self.person_type.id, "status", "Active", "#00FF00")

        payload = self.compile()

        self.assertEqual(self.node(payload, no_value).style.background, "#123456")
        self.assertEqual(self.node(payload, unmapped).style.background, "#123456")

    def test_different_attributes_drive_background_and_border(self):
        alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active", "urgent": True})
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_source", "attribute")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_attribute", "status")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "border_source", "attribute")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "border_attribute", "urgent")
        self.set_attribute_colour(OBJECT_TYPE, self.person_type.id, "status", "Active", "#00FF00")
        self.set_attribute_colour(OBJECT_TYPE, self.person_type.id, "urgent", "true", "#FF0000")

        style = self.node(self.compile(), alice).style

        self.assertEqual((style.background, style.border), ("#00FF00", "#FF0000"))

    def test_same_attribute_drives_background_and_border(self):
        alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_source", "attribute")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background_attribute", "status")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "border_source", "attribute")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "border_attribute", "status")
        self.set_attribute_colour(OBJECT_TYPE, self.person_type.id, "status", "Active", "#00FF00")

        style = self.node(self.compile(), alice).style

        self.assertEqual((style.background, style.border), ("#00FF00", "#00FF00"))

    def test_relationship_line_colour_is_attribute_driven(self):
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        high = self.make_relationship(alice, ops, attributes={"importance": "High"})
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.member_of.id, "colour_source", "attribute")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.member_of.id, "colour_attribute", "importance")
        self.set_attribute_colour(RELATIONSHIP_TYPE, self.member_of.id, "importance", "High", "#FF0000")

        edge = self.edge(self.compile(), high)

        self.assertEqual(edge.style.colour, "#FF0000")

    def test_relationship_with_no_value_falls_back_to_type_colour(self):
        alice = self.make_object(self.person_type, "Alice")
        ops = self.make_object(self.team_type, "Ops")
        no_value = self.make_relationship(alice, ops)
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.member_of.id, "colour_source", "attribute")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.member_of.id, "colour_attribute", "importance")
        self.set_attribute_colour(RELATIONSHIP_TYPE, self.member_of.id, "importance", "High", "#FF0000")

        edge = self.edge(self.compile(), no_value)

        self.assertEqual(edge.style.colour, "#495057")

    def test_type_sourced_colours_are_unaffected_by_the_new_fields(self):
        self.seed()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background", "#123456")

        style = self.node(self.compile(), self.alice).style

        self.assertEqual(style.background, "#123456")


class ProposedVisualStateTests(CompilerTestCase):

    def test_no_active_proposal_shows_canonical_state_only(self):
        self.seed()
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Draft")

        payload = self.compile(None)

        self.assertEqual(len(payload.nodes), 2)
        self.assertFalse(any(n.data["is_proposed"] for n in payload.nodes))

    def test_proposed_object_is_amber_and_canonical_keeps_type_appearance(self):
        self.seed()
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "background", "#1c7ed6")
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.person_type.id, "Draft")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.person_type.id, "shape", "square")

        payload = self.compile(proposal)

        draft = next(n for n in payload.nodes if n.id == str(draft_id))
        self.assertTrue(draft.data["is_proposed"] and draft.data["is_created"])
        self.assertEqual((draft.style.background, draft.style.border), (AMBER_BACKGROUND, AMBER))
        self.assertEqual(draft.style.shape, "square")  # type identity preserved
        canonical = self.node(payload, self.alice).style
        self.assertEqual((canonical.background, canonical.border, canonical.shape), ("#1C7ED6", "#4C6EF5", "square"))

    def test_updated_canonical_object_is_marked_proposed(self):
        self.seed()
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "attributes.status", "Left")

        payload = self.compile(proposal)

        alice = self.node(payload, self.alice)
        self.assertTrue(alice.data["is_proposed"])
        self.assertFalse(alice.data["is_created"])
        self.assertEqual(alice.data["attributes"], {"status": "Left"})
        self.assertEqual(alice.style.border, AMBER)
        self.assertFalse(self.node(payload, self.ops).data["is_proposed"])

    def test_proposed_relationship_is_amber_dashed_and_canonical_is_not(self):
        self.seed()
        bob = self.make_object(self.person_type, "Bob")
        proposal = self.working_proposal()
        relationship_id = self.propose_relationship(proposal, bob.id, self.ops.id)

        payload = self.compile(proposal)

        proposed = next(e for e in payload.edges if e.id == str(relationship_id))
        self.assertEqual((proposed.style.colour, proposed.style.dashes), (AMBER, True))
        canonical = self.edge(payload, self.membership)
        self.assertEqual(canonical.style.colour, "#495057")
        self.assertIsNone(canonical.style.dashes)

    def test_proposed_edge_keeps_its_relationship_type_appearance(self):
        self.seed()
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.member_of.id, "width", 4)
        bob = self.make_object(self.person_type, "Bob")
        proposal = self.working_proposal()
        relationship_id = self.propose_relationship(proposal, bob.id, self.ops.id)

        edge = next(e for e in self.compile(proposal).edges if e.id == str(relationship_id))

        self.assertEqual(edge.style.width, 4)

    def test_proposed_deactivation_removes_the_object_from_the_graph(self):
        self.seed()
        proposal = self.working_proposal()
        self.update(proposal, "Object", self.alice.id, "is_active", False)

        payload = self.compile(proposal)

        self.assertEqual([n.id for n in payload.nodes], [str(self.ops.id)])
        self.assertEqual(payload.edges, [])

    def test_proposed_type_rename_alone_does_not_flag_every_instance(self):
        self.seed()
        proposal = self.working_proposal()
        self.update(proposal, "ObjectType", self.person_type.id, "name", "Human")
        self.update(proposal, "RelationshipType", self.member_of.id, "name", "Belongs to")

        payload = self.compile(proposal)

        self.assertFalse(any(n.data["is_proposed"] for n in payload.nodes))
        self.assertFalse(any(e.data["is_proposed"] for e in payload.edges))
        self.assertEqual(self.node(payload, self.alice).data["object_type_name"], "Human")
        self.assertEqual(payload.edges[0].label, "Belongs to")

    def test_proposed_object_interacts_with_canonical_ones(self):
        self.seed()
        proposal = self.working_proposal()
        draft_id = self.propose_object(proposal, self.team_type.id, "Draft Team")
        relationship_id = self.propose_relationship(proposal, self.alice.id, draft_id)

        payload = self.compile(proposal)

        edge = next(e for e in payload.edges if e.id == str(relationship_id))
        self.assertEqual((edge.source, edge.target), (str(self.alice.id), str(draft_id)))
        self.assertEqual(validate_payload(payload), [])
