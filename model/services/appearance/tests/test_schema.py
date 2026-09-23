from django.test import SimpleTestCase

from model.services.appearance import schema
from model.services.appearance.schema import AppearanceValidationError


class CleanValueTests(SimpleTestCase):

    def test_colours_are_normalised_to_uppercase_six_digit_hex(self):
        self.assertEqual(schema.clean_value(schema.OBJECT, "background", "#abc"), "#AABBCC")
        self.assertEqual(schema.clean_value(schema.OBJECT, "background", " #4c6ef5 "), "#4C6EF5")

    def test_bad_colours_are_rejected(self):
        for bad in ("red", "#12", "#GGGGGG", "4C6EF5", 12, None):
            with self.assertRaises(AppearanceValidationError, msg=repr(bad)):
                schema.clean_value(schema.OBJECT, "background", bad)

    def test_numbers_are_range_checked(self):
        self.assertEqual(schema.clean_value(schema.OBJECT, "border_width", "2"), 2)
        self.assertEqual(schema.clean_value(schema.OBJECT, "border_width", "1.5"), 1.5)
        for bad in ("-1", "9", "abc", True, float("nan")):
            with self.assertRaises(AppearanceValidationError, msg=repr(bad)):
                schema.clean_value(schema.OBJECT, "border_width", bad)

    def test_choices_must_be_from_the_curated_set(self):
        self.assertEqual(schema.clean_value(schema.OBJECT, "shape", "hexagon"), "hexagon")
        with self.assertRaises(AppearanceValidationError):
            schema.clean_value(schema.OBJECT, "shape", "blob")

    def test_font_family_is_a_curated_stack_not_free_text(self):
        for stack, _label in schema.FONT_STACKS:
            self.assertEqual(schema.clean_value(schema.THEME, "font_family", stack), stack)
        for bad in ("Comic Sans MS", "Arial", "Arial, sans-serif", "", "url(x)"):
            with self.assertRaises(AppearanceValidationError, msg=repr(bad)):
                schema.clean_value(schema.THEME, "font_family", bad)

    def test_every_font_stack_has_a_generic_fallback(self):
        for stack, _label in schema.FONT_STACKS:
            self.assertRegex(stack, r"(sans-serif|serif|monospace)$")

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(AppearanceValidationError):
            schema.clean_value(schema.OBJECT, "glow", "#FFFFFF")

    def test_icon_is_type_level_only(self):
        self.assertEqual(schema.clean_value(schema.OBJECT, "icon", "person"), "person")
        with self.assertRaises(AppearanceValidationError):
            schema.clean_value(schema.OBJECT, "icon", "person", model_level=True)
        with self.assertRaises(AppearanceValidationError):
            schema.clean_value(schema.OBJECT, "icon", "no-such-icon")

    def test_colour_source_fields_are_type_level_only_selects(self):
        for scope, field in (
            (schema.OBJECT, "background_source"),
            (schema.OBJECT, "border_source"),
            (schema.RELATIONSHIP, "colour_source"),
        ):
            self.assertEqual(schema.clean_value(scope, field, "attribute"), "attribute")
            self.assertEqual(schema.clean_value(scope, field, "type"), "type")
            with self.assertRaises(AppearanceValidationError):
                schema.clean_value(scope, field, "bogus")
            with self.assertRaises(AppearanceValidationError):
                schema.clean_value(scope, field, "attribute", model_level=True)

    def test_attribute_control_accepts_any_well_shaped_key(self):
        for scope, field in (
            (schema.OBJECT, "background_attribute"),
            (schema.OBJECT, "border_attribute"),
            (schema.RELATIONSHIP, "colour_attribute"),
        ):
            self.assertEqual(schema.clean_value(scope, field, "test_status"), "test_status")
            self.assertEqual(schema.clean_value(scope, field, " test-status "), "test-status")
            for bad in ("", "   ", "has space", "semi;colon", 5, None):
                with self.assertRaises(AppearanceValidationError, msg=repr(bad)):
                    schema.clean_value(scope, field, bad)
            with self.assertRaises(AppearanceValidationError):
                schema.clean_value(scope, field, "test_status", model_level=True)


class SanitiseTests(SimpleTestCase):

    def test_non_dict_documents_become_empty(self):
        for raw in (None, [], "x", 3):
            self.assertEqual(schema.sanitise_document(raw), schema.empty_document())

    def test_invalid_and_unknown_entries_are_dropped(self):
        document = schema.sanitise_document(
            {
                "theme": {"accent": "#abc", "font_family": "Comic Sans", "bogus": 1},
                "objects": {"shape": "star", "icon": "person"},
                "object_types": {"id-1": {"shape": "nope", "border": "#000"}, "id-2": {"shape": "nope"}},
                "relationships": "not a dict",
            }
        )

        self.assertEqual(document["theme"], {"accent": "#AABBCC"})
        self.assertEqual(document["objects"], {"shape": "star"})  # icon not allowed model-wide
        self.assertEqual(document["object_types"], {"id-1": {"border": "#000000"}})
        self.assertEqual(document["relationships"], {})

    def test_empty_document_has_an_empty_attribute_colours_section(self):
        self.assertEqual(schema.empty_document()[schema.ATTRIBUTE_COLOURS], {"object_type": {}, "relationship_type": {}})

    def test_attribute_colours_round_trip(self):
        raw = {
            schema.ATTRIBUTE_COLOURS: {
                "object_type": {"type-1": {"status": {"Passed": "#abc", "Failed": "#f00000"}}},
                "relationship_type": {"type-2": {"integration": {"true": "#00ff00"}}},
            }
        }
        document = schema.sanitise_document(raw)

        self.assertEqual(
            schema.attribute_colours(document, schema.OBJECT_TYPE, "type-1", "status"),
            {"Passed": "#AABBCC", "Failed": "#F00000"},
        )
        self.assertEqual(
            schema.attribute_colours(document, schema.RELATIONSHIP_TYPE, "type-2", "integration"),
            {"true": "#00FF00"},
        )
        self.assertEqual(schema.attribute_colours(document, schema.OBJECT_TYPE, "type-1", "no-such-attribute"), {})
        self.assertEqual(schema.attribute_colours(document, schema.OBJECT_TYPE, "no-such-type", "status"), {})

    def test_malformed_attribute_colours_are_discarded_silently(self):
        raw = {
            schema.ATTRIBUTE_COLOURS: {
                "object_type": {
                    "type-1": {
                        "status": {"Passed": "#abc", "Failed": "not-a-colour", 5: "#000000", "": "#000000"},
                        3: {"x": "#000000"},
                    },
                    5: {"status": {"x": "#000000"}},
                },
                "relationship_type": "not-a-dict",
            }
        }
        document = schema.sanitise_document(raw)

        self.assertEqual(
            schema.attribute_colours(document, schema.OBJECT_TYPE, "type-1", "status"),
            {"Passed": "#AABBCC"},
        )
        self.assertEqual(document[schema.ATTRIBUTE_COLOURS]["relationship_type"], {})

    def test_non_dict_document_still_has_a_well_formed_attribute_colours_section(self):
        for raw in (None, [], "x", 3):
            self.assertEqual(
                schema.sanitise_document(raw)[schema.ATTRIBUTE_COLOURS], {"object_type": {}, "relationship_type": {}}
            )
