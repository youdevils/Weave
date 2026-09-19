from django.test import SimpleTestCase

from model.services.appearance import defaults
from model.services.appearance.resolver import resolve_object, resolve_relationship, resolve_theme
from model.services.appearance.viewer_adapter import edge_style, node_style


class NodeStyleTests(SimpleTestCase):

    def setUp(self):
        self.theme = resolve_theme({})

    def node(self, **type_layer):
        return resolve_object(self.theme, {}, type_layer)

    def test_default_node_matches_previous_hard_coded_style(self):
        style = node_style(self.node())
        self.assertEqual(style.shape, "box")
        self.assertEqual(style.background, "#EDF2FF")
        self.assertEqual(style.border, "#4C6EF5")
        self.assertEqual(style.border_width, 1.5)
        self.assertEqual(style.font["color"], "#212529")
        self.assertEqual(style.font["size"], 14)
        self.assertNotIn("weight", style.font)
        self.assertIsNone(style.image)

    def test_font_face_comes_from_resolved_font_family(self):
        theme = resolve_theme({"font_family": "'Courier New', Courier, monospace"})
        style = node_style(resolve_object(theme, {}, {}))
        self.assertEqual(style.font["face"], "'Courier New', Courier, monospace")

    def test_bold_is_carried_as_font_weight(self):
        self.assertEqual(node_style(self.node(font_weight="bold")).font["weight"], "bold")

    def test_proposed_node_uses_amber_but_keeps_type_identity(self):
        style = node_style(
            self.node(shape="square", size=40, font_weight="bold", font_size=20),
            is_proposed=True,
        )
        self.assertEqual(style.background, defaults.PROPOSED_NODE_BACKGROUND)
        self.assertEqual(style.border, defaults.PROPOSED_NODE_BORDER)
        self.assertEqual(style.shape, "square")
        self.assertEqual(style.size, 40)
        self.assertEqual(style.font["size"], 20)
        self.assertEqual(style.font["weight"], "bold")

    def test_canonical_node_ignores_proposal_palette(self):
        style = node_style(self.node(background="#111111", border="#222222"))
        self.assertEqual((style.background, style.border), ("#111111", "#222222"))

    def test_icon_becomes_circular_image_in_border_colour(self):
        style = node_style(self.node(icon="database", border="#AA0000"))
        self.assertEqual(style.shape, "circularImage")
        self.assertTrue(style.image.startswith("data:image/svg+xml"))
        self.assertIn("%23AA0000", style.image)

    def test_proposed_icon_node_uses_proposed_border_for_the_glyph(self):
        style = node_style(self.node(icon="person"), is_proposed=True)
        self.assertIn("%23F08C00", style.image)


class EdgeStyleTests(SimpleTestCase):

    def setUp(self):
        self.theme = resolve_theme({})

    def edge(self, **type_layer):
        return resolve_relationship(self.theme, {}, type_layer)

    def test_default_edge_matches_previous_hard_coded_style(self):
        style = edge_style(self.edge())
        self.assertEqual(style.colour, "#495057")
        self.assertEqual(style.width, 1.5)
        self.assertIsNone(style.dashes)
        self.assertEqual(style.arrows, "to")
        self.assertEqual(style.font["color"], "#495057")
        self.assertEqual(style.font["size"], 11)

    def test_line_styles(self):
        self.assertIsNone(edge_style(self.edge(line_style="solid")).dashes)
        self.assertEqual(edge_style(self.edge(line_style="dashed")).dashes, [8, 6])
        self.assertEqual(edge_style(self.edge(line_style="dotted")).dashes, [2, 4])

    def test_arrow_options(self):
        self.assertIsNone(edge_style(self.edge(arrows="none")).arrows)
        self.assertEqual(edge_style(self.edge(arrows="to")).arrows, "to")
        self.assertEqual(edge_style(self.edge(arrows="from")).arrows, "from")
        self.assertEqual(edge_style(self.edge(arrows="both")).arrows, "to, from")

    def test_proposed_edge_is_amber_and_dashed_but_keeps_width_and_arrows(self):
        style = edge_style(self.edge(width=4, arrows="both", colour="#123456"), is_proposed=True)
        self.assertEqual(style.colour, defaults.PROPOSED_EDGE_COLOUR)
        self.assertIs(style.dashes, True)
        self.assertEqual(style.width, 4)
        self.assertEqual(style.arrows, "to, from")

    def test_font_face_and_label_style(self):
        theme = resolve_theme({"font_family": "Verdana, Geneva, sans-serif"})
        style = edge_style(resolve_relationship(theme, {"label_colour": "#010101", "label_size": 16}, {}))
        self.assertEqual(
            style.font,
            {"color": "#010101", "size": 16, "face": "Verdana, Geneva, sans-serif", "strokeColor": "#FFFFFF"},
        )

    def test_label_halo_follows_the_canvas_background(self):
        theme = resolve_theme({"canvas_background": "#101010"})
        style = edge_style(resolve_relationship(theme, {}, {}))
        self.assertEqual(style.font["strokeColor"], "#101010")
