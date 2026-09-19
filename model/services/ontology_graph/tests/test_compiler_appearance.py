import uuid

from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.appearance import OBJECT_TYPE, RELATIONSHIP_TYPE, AppearanceService
from model.services.ontology_graph.compiler import compile_ontology_graph
from viewer.contracts import ViewerPayload, validate_payload
from workspace.models import Workspace

AMBER_BACKGROUND = "#FFF3BF"
AMBER = "#F08C00"


class CompilerAppearanceTests(TestCase):
    """The ontology compiler takes its styles from the shared appearance resolver."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="user@example.com", password="test-password")
        cls.model = Model.objects.create(workspace=cls.workspace, name="Test Model", revision=1)

    def setUp(self):
        self.process = ObjectType.objects.create(model=self.model, name="Process", key="process", is_active=True)
        self.system = ObjectType.objects.create(model=self.model, name="System", key="system", is_active=True)
        self.contains = RelationshipType.objects.create(
            model=self.model, name="Contains", key="contains", is_active=True
        )
        self.rule = RelationshipTypeRule.objects.create(
            relationship_type=self.contains, subject_type=self.process, object_type=self.system
        )

    def compile(self, proposal=None):
        payload = compile_ontology_graph(self.model, proposal)
        self.assertEqual(validate_payload(payload), [])
        return payload

    def node(self, payload, object_type):
        return next(node for node in payload.nodes if node.id == str(object_type.id))

    def edge(self, payload, rule=None):
        return next(edge for edge in payload.edges if edge.id == str((rule or self.rule).id))

    def working_proposal(self):
        return Proposal.objects.create(model=self.model, created_by=self.user, status=Proposal.Status.WORKING)

    def add_change(self, proposal, **kwargs):
        defaults = {"proposal": proposal, "source": ProposalChange.Source.USER}
        defaults.update(kwargs)
        return ProposalChange.objects.create(**defaults)

    def propose_object_type(self, proposal, key="draft"):
        type_id = uuid.uuid4()
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=type_id,
            parent_type="Model",
            parent_id=self.model.id,
            after={"name": key.title(), "key": key, "description": "", "sort_order": 0, "is_active": True},
        )
        return type_id

    # -----------------------------------------------------------------
    # Defaults and resolved styles
    # -----------------------------------------------------------------

    def test_unstyled_model_keeps_the_previous_look(self):
        payload = self.compile()
        style = self.node(payload, self.process).style
        self.assertEqual(
            (style.shape, style.background, style.border, style.border_width),
            ("box", "#EDF2FF", "#4C6EF5", 1.5),
        )
        self.assertEqual((style.font["color"], style.font["size"]), ("#212529", 14))

        edge = self.edge(payload).style
        self.assertEqual((edge.colour, edge.width, edge.arrows), ("#495057", 1.5, "to"))
        self.assertIsNone(edge.dashes)
        self.assertEqual((edge.font["color"], edge.font["size"]), ("#495057", 11))

    def test_each_type_is_styled_independently(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "shape", "square")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "background", "#1c7ed6")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "size", 40)

        payload = self.compile()

        process_style = self.node(payload, self.process).style
        self.assertEqual(
            (process_style.shape, process_style.background, process_style.size), ("square", "#1C7ED6", 40)
        )
        system_style = self.node(payload, self.system).style
        self.assertEqual((system_style.shape, system_style.background), ("box", "#EDF2FF"))

    def test_object_type_font_border_and_weight_overrides(self):
        for field, value in (
            ("border", "#222222"),
            ("border_width", 4),
            ("font_colour", "#ffffff"),
            ("font_size", 20),
            ("font_weight", "bold"),
        ):
            AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, field, value)

        style = self.node(self.compile(), self.process).style

        self.assertEqual((style.border, style.border_width), ("#222222", 4))
        self.assertEqual(style.font["color"], "#FFFFFF")
        self.assertEqual(style.font["size"], 20)
        self.assertEqual(style.font["weight"], "bold")

    def test_icon_becomes_an_image_node(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "icon", "database")

        payload = self.compile()
        style = self.node(payload, self.process).style
        self.assertEqual(style.shape, "circularImage")
        self.assertTrue(style.image.startswith("data:image/svg+xml"))
        self.assertIsNone(self.node(payload, self.system).style.image)
        # The image field survives the contract round trip.
        restored = ViewerPayload.from_dict(payload.to_dict())
        self.assertEqual(self.node(restored, self.process).style.image, style.image)

    def test_relationship_type_overrides(self):
        for field, value in (
            ("colour", "#c92a2a"),
            ("width", 4),
            ("line_style", "dotted"),
            ("arrows", "both"),
            ("label_colour", "#111111"),
            ("label_size", 16),
        ):
            AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.contains.id, field, value)

        style = self.edge(self.compile()).style

        self.assertEqual((style.colour, style.width), ("#C92A2A", 4))
        self.assertEqual(style.dashes, [2, 4])
        self.assertEqual(style.arrows, "to, from")
        self.assertEqual((style.font["color"], style.font["size"]), ("#111111", 16))

    def test_model_customisation_applies_to_types_without_overrides(self):
        AppearanceService.update_customisation(self.model, "object", "shape", "ellipse")
        AppearanceService.update_customisation(self.model, "relationship", "line_style", "dashed")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "shape", "square")

        payload = self.compile()

        self.assertEqual(self.node(payload, self.process).style.shape, "square")
        self.assertEqual(self.node(payload, self.system).style.shape, "ellipse")
        self.assertEqual(self.edge(payload).style.dashes, [8, 6])

    def test_theme_accent_and_font_family_reach_nodes_and_edges(self):
        stack = "'Courier New', Courier, monospace"
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")
        AppearanceService.update_customisation(self.model, "theme", "font_family", stack)

        payload = self.compile()

        self.assertEqual(self.node(payload, self.process).style.border, "#00AA00")
        self.assertEqual(self.node(payload, self.process).style.font["face"], stack)
        self.assertEqual(self.edge(payload).style.font["face"], stack)

    def test_canvas_background_is_exposed_for_the_host_page(self):
        self.assertEqual(self.compile().viewer_config.extra["canvas_background"], "#FFFFFF")

        AppearanceService.update_customisation(self.model, "theme", "canvas_background", "#101010")
        self.assertEqual(self.compile().viewer_config.extra["canvas_background"], "#101010")

    def test_edge_label_halo_matches_the_canvas_so_labels_stay_clean_on_dark_graphs(self):
        self.assertEqual(self.edge(self.compile()).style.font["strokeColor"], "#FFFFFF")

        AppearanceService.update_customisation(self.model, "theme", "canvas_background", "#101010")
        self.assertEqual(self.edge(self.compile()).style.font["strokeColor"], "#101010")

    def test_styles_are_shared_visual_identity_not_per_viewer(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "shape", "star")

        # Resolving straight from the service gives the same identity the compiler used.
        resolved = AppearanceService.resolve_object_type(self.model, self.process.id)
        self.assertEqual(self.node(self.compile(), self.process).style.shape, resolved.shape)

    # -----------------------------------------------------------------
    # Proposal overlay
    # -----------------------------------------------------------------

    def test_canonical_elements_keep_type_appearance_when_a_proposal_is_active(self):
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "background", "#1c7ed6")
        proposal = self.working_proposal()
        self.propose_object_type(proposal)

        payload = self.compile(proposal)

        style = self.node(payload, self.process).style
        self.assertEqual((style.background, style.border), ("#1C7ED6", "#4C6EF5"))
        self.assertFalse(self.node(payload, self.process).data["is_proposed"])
        self.assertIsNone(self.edge(payload).style.dashes)

    def test_proposed_node_uses_amber_but_keeps_its_type_identity(self):
        proposal = self.working_proposal()
        type_id = self.propose_object_type(proposal)
        # Styled before it exists canonically.
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, type_id, "shape", "square")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, type_id, "size", 40)
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, type_id, "font_weight", "bold")

        payload = self.compile(proposal)

        node = next(node for node in payload.nodes if node.id == str(type_id))
        self.assertTrue(node.data["is_proposed"])
        self.assertEqual((node.style.background, node.style.border), (AMBER_BACKGROUND, AMBER))
        self.assertEqual((node.style.shape, node.style.size), ("square", 40))
        self.assertEqual(node.style.font["weight"], "bold")

    def test_proposed_rule_edge_is_amber_and_dashed_but_keeps_type_width_and_arrows(self):
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.contains.id, "width", 4)
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.contains.id, "arrows", "both")
        third = ObjectType.objects.create(model=self.model, name="Third", key="third", is_active=True)
        proposal = self.working_proposal()
        rule_id = uuid.uuid4()
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipTypeRule",
            target_id=rule_id,
            parent_type="RelationshipType",
            parent_id=self.contains.id,
            after={
                "subject_type_id": str(self.process.id),
                "object_type_id": str(third.id),
                "subject_minimum": 0,
                "object_minimum": 0,
            },
        )

        payload = self.compile(proposal)

        proposed_edge = next(edge for edge in payload.edges if edge.id == str(rule_id))
        self.assertEqual((proposed_edge.style.colour, proposed_edge.style.dashes), (AMBER, True))
        self.assertEqual((proposed_edge.style.width, proposed_edge.style.arrows), (4, "to, from"))
        # The canonical rule of the same type is untouched.
        canonical_edge = self.edge(payload)
        self.assertEqual(canonical_edge.style.colour, "#495057")
        self.assertIsNone(canonical_edge.style.dashes)

    def test_proposed_relationship_type_update_marks_its_canonical_rules_proposed(self):
        proposal = self.working_proposal()
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="RelationshipType",
            target_id=self.contains.id,
            after={"field": "name", "value": "Holds"},
        )

        payload = self.compile(proposal)

        edge = self.edge(payload)
        self.assertEqual(edge.label, "Holds")
        self.assertTrue(edge.data["is_proposed"])
        self.assertEqual((edge.style.colour, edge.style.dashes), (AMBER, True))

    def test_edge_is_canonical_when_neither_type_nor_rule_is_proposed(self):
        proposal = self.working_proposal()
        self.propose_object_type(proposal)

        edge = self.edge(self.compile(proposal))

        self.assertFalse(edge.data["is_proposed"])
        self.assertEqual(edge.style.colour, "#495057")

    def test_proposed_type_and_proposed_rule_together_is_still_a_single_proposed_edge(self):
        proposal = self.working_proposal()
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="RelationshipType",
            target_id=self.contains.id,
            after={"field": "name", "value": "Holds"},
        )
        third = ObjectType.objects.create(model=self.model, name="Third", key="third", is_active=True)
        rule_id = uuid.uuid4()
        self.add_change(
            proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="RelationshipTypeRule",
            target_id=rule_id,
            parent_type="RelationshipType",
            parent_id=self.contains.id,
            after={"subject_type_id": str(self.process.id), "object_type_id": str(third.id)},
        )

        payload = self.compile(proposal)

        self.assertEqual(len(payload.edges), 2)
        self.assertTrue(all(edge.style.dashes is True for edge in payload.edges))

    # -----------------------------------------------------------------
    # Contract
    # -----------------------------------------------------------------

    def test_fully_styled_payload_stays_valid_and_round_trips(self):
        AppearanceService.update_customisation(self.model, "theme", "accent", "#00aa00")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.process.id, "icon", "person")
        AppearanceService.set_type_style(self.model, OBJECT_TYPE, self.system.id, "shape", "hexagon")
        AppearanceService.set_type_style(self.model, RELATIONSHIP_TYPE, self.contains.id, "line_style", "dotted")
        proposal = self.working_proposal()
        self.propose_object_type(proposal)

        payload = self.compile(proposal)

        self.assertEqual(validate_payload(ViewerPayload.from_dict(payload.to_dict())), [])
