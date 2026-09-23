from django.test import SimpleTestCase

from model.services.appearance import defaults
from model.services.appearance.resolver import (
    resolve_object,
    resolve_relationship,
    resolve_theme,
)


class ThemeResolutionTests(SimpleTestCase):

    def test_built_in_defaults(self):
        theme = resolve_theme({})
        self.assertEqual(theme.to_dict(), defaults.THEME_DEFAULTS)

    def test_model_customisation_overrides_built_in(self):
        theme = resolve_theme({"accent": "#FF0000"})
        self.assertEqual(theme.accent, "#FF0000")
        self.assertEqual(theme.canvas_background, defaults.THEME_DEFAULTS["canvas_background"])


class ObjectResolutionTests(SimpleTestCase):

    def setUp(self):
        self.theme = resolve_theme({})

    def test_new_type_with_no_config_resolves_to_todays_look(self):
        resolved = resolve_object(self.theme, {}, {})
        self.assertEqual(resolved.shape, "box")
        self.assertEqual(resolved.background, "#EDF2FF")
        self.assertEqual(resolved.border, "#4C6EF5")
        self.assertEqual(resolved.border_width, 1.5)
        self.assertEqual(resolved.font_colour, "#212529")
        self.assertEqual(resolved.font_size, 14)
        self.assertEqual(resolved.font_weight, "normal")
        self.assertIsNone(resolved.icon)

    def test_model_layer_overrides_built_in(self):
        resolved = resolve_object(self.theme, {"shape": "ellipse", "font_size": 18}, {})
        self.assertEqual(resolved.shape, "ellipse")
        self.assertEqual(resolved.font_size, 18)
        self.assertEqual(resolved.background, "#EDF2FF")

    def test_type_layer_overrides_model_layer(self):
        resolved = resolve_object(self.theme, {"shape": "ellipse", "background": "#111111"}, {"shape": "square"})
        self.assertEqual(resolved.shape, "square")
        self.assertEqual(resolved.background, "#111111")

    def test_border_falls_back_to_theme_accent(self):
        theme = resolve_theme({"accent": "#00AA00"})
        self.assertEqual(resolve_object(theme, {}, {}).border, "#00AA00")
        self.assertEqual(resolve_object(theme, {"border": "#222222"}, {}).border, "#222222")
        self.assertEqual(resolve_object(theme, {"border": "#222222"}, {"border": "#333333"}).border, "#333333")

    def test_font_family_flows_from_theme(self):
        stack = "Georgia, 'Times New Roman', serif"
        theme = resolve_theme({"font_family": stack})
        self.assertEqual(resolve_object(theme, {}, {}).font_family, stack)
        self.assertEqual(resolve_relationship(theme, {}, {}).font_family, stack)

    def test_colour_source_defaults_to_type_with_no_attribute_and_no_value_map(self):
        resolved = resolve_object(self.theme, {}, {})
        self.assertEqual(resolved.background_source, "type")
        self.assertIsNone(resolved.background_attribute)
        self.assertEqual(resolved.background_by_value, {})
        self.assertEqual(resolved.border_source, "type")
        self.assertIsNone(resolved.border_attribute)
        self.assertEqual(resolved.border_by_value, {})

    def test_colour_source_and_attribute_flow_through_the_same_layering(self):
        resolved = resolve_object(
            self.theme,
            {"background_source": "attribute", "background_attribute": "model-level-attr"},
            {"background_attribute": "type-level-attr"},
        )
        self.assertEqual(resolved.background_source, "attribute")
        self.assertEqual(resolved.background_attribute, "type-level-attr")

    def test_by_value_maps_default_to_independent_empty_dicts(self):
        """A mutable-default bug would alias one dict across every resolution."""
        first = resolve_object(self.theme, {}, {})
        second = resolve_object(self.theme, {}, {})
        self.assertIsNot(first.background_by_value, second.background_by_value)
        first.background_by_value["leaked"] = "#000000"
        self.assertEqual(second.background_by_value, {})


class RelationshipResolutionTests(SimpleTestCase):

    def setUp(self):
        self.theme = resolve_theme({})

    def test_new_type_with_no_config_resolves_to_todays_look(self):
        resolved = resolve_relationship(self.theme, {}, {})
        self.assertEqual(resolved.colour, "#495057")
        self.assertEqual(resolved.width, 1.5)
        self.assertEqual(resolved.line_style, "solid")
        self.assertEqual(resolved.arrows, "to")
        self.assertEqual(resolved.label_colour, "#495057")
        self.assertEqual(resolved.label_size, 11)

    def test_label_halo_is_the_canvas_background(self):
        self.assertEqual(resolve_relationship(self.theme, {}, {}).label_halo, "#FFFFFF")
        dark = resolve_theme({"canvas_background": "#101010"})
        self.assertEqual(resolve_relationship(dark, {}, {}).label_halo, "#101010")

    def test_layering(self):
        resolved = resolve_relationship(
            self.theme,
            {"line_style": "dashed", "width": 3},
            {"line_style": "dotted", "arrows": "both"},
        )
        self.assertEqual(resolved.line_style, "dotted")
        self.assertEqual(resolved.width, 3)
        self.assertEqual(resolved.arrows, "both")

    def test_colour_source_defaults_to_type_with_no_attribute_and_no_value_map(self):
        resolved = resolve_relationship(self.theme, {}, {})
        self.assertEqual(resolved.colour_source, "type")
        self.assertIsNone(resolved.colour_attribute)
        self.assertEqual(resolved.colour_by_value, {})

    def test_colour_source_and_attribute_flow_through_the_same_layering(self):
        resolved = resolve_relationship(
            self.theme,
            {"colour_source": "attribute", "colour_attribute": "model-level"},
            {"colour_attribute": "type-level"},
        )
        self.assertEqual(resolved.colour_source, "attribute")
        self.assertEqual(resolved.colour_attribute, "type-level")
